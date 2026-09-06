// B站粉丝数实时刷新：bilibili 官方接口不带 CORS 头，需经 CORS 代理访问
const biliApiUrl = () =>
    `https://api.bilibili.com/x/relation/stat?vmid=${BILIBILI_UID}&time=${Date.now()}`;

// CORS 代理候选，按顺序尝试，成功即停（免费代理偶发故障，故保留后备）
const PROXY_LIST = [
    (u) => `https://api.allorigins.win/raw?url=${encodeURIComponent(u)}`,
    (u) => `https://api.codetabs.com/v1/proxy/?quest=${encodeURIComponent(u)}`,
];

async function fetchWithTimeout(url, ms = 10000) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), ms);
    try {
        return await fetch(url, { signal: ctrl.signal });
    } finally {
        clearTimeout(timer);
    }
}

const fansDisplay = document.getElementById('fansDisplay');
const progressFill = document.getElementById('progressFill');
const changeToast = document.getElementById('changeToast');

let currentFans = parseInt(fansDisplay.innerText, 10);

function updateProgress(fans) {
    const percent = (fans / TOTAL_GOAL) * 100;
    progressFill.style.width = `${percent.toFixed(2)}%`;
}

function showChange(change) {
    if (change === 0) return;
    const sign = change > 0 ? '+' : '';
    changeToast.textContent = `${sign}${change}`;
    changeToast.classList.add('show');
    setTimeout(() => {
        changeToast.classList.remove('show');
    }, 500);
}

async function fetchFans() {
    // 逐个代理尝试：拿到 code===0 即成功；单次请求 8s 超时
    for (const buildUrl of PROXY_LIST) {
        let ok = false;
        try {
            const response = await fetchWithTimeout(buildUrl(biliApiUrl()));
            const data = await response.json();
            if (data.code === 0) {
                const newFans = data.data.follower;
                if (newFans !== currentFans) {
                    const change = newFans - currentFans;
                    currentFans = newFans;
                    fansDisplay.innerText = newFans;
                    updateProgress(newFans);
                    showChange(change);
                }
                ok = true; // 通道可用，结束尝试
            } else {
                console.error('API error:', data);
                ok = true; // 通道正常但接口报错，换通道无意义
            }
        } catch (error) {
            console.error('Proxy failed, try next:', buildUrl(biliApiUrl()), error);
        }
        if (ok) break;
    }
    setTimeout(() => {
        fetchFans();
    }, 5000);
}

// 初始化进度条
updateProgress(currentFans);

// 立即获取一次最新数据（可选，保证打开页面时与真实值同步）
fetchFans();

/* ========== 历史图表：纯 JS 绘制 SVG 折线图 ========== */
// 数据记录于 Asia/Shanghai：偏移 +8h 后按 UTC 读取年月日/时分
function formatChartTime(ts) {
    const d = new Date(ts * 1000 + 8 * 3600 * 1000);
    const p = (n) => String(n).padStart(2, '0');
    return `${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

// 完整可读时间（北京时间），用于悬停弹窗
function formatChartFullTime(ts) {
    const d = new Date(ts * 1000 + 8 * 3600 * 1000);
    const p = (n) => String(n).padStart(2, '0');
    return `${d.getUTCFullYear()}-${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}`;
}

function formatChartCompact(n) {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`;
    return String(Math.round(n));
}

function drawHistoryChart() {
    const container = document.getElementById('historyChart');
    if (!container) return;
    // HISTORY_DATA 由页面内联脚本以顶层 var 声明（挂载于 window）；typeof 兜底防 ReferenceError
    const data = typeof HISTORY_DATA !== 'undefined' ? HISTORY_DATA : [];
    if (data.length < 2) {
        const empty = document.createElement('div');
        empty.className = 'chart-empty';
        empty.textContent = data.length ? '历史数据不足，暂无法绘制图表' : '暂无历史数据';
        container.replaceChildren(empty);
        return;
    }

    const NS = 'http://www.w3.org/2000/svg';
    const W = 900;
    const H = 300;
    const M = { top: 16, right: 24, bottom: 40, left: 72 };
    const innerW = W - M.left - M.right;
    const innerH = H - M.top - M.bottom;

    const times = data.map((p) => p.t);
    const counts = data.map((p) => p.c);
    const tMin = Math.min(...times);
    const tMax = Math.max(...times);
    const tSpan = tMax - tMin || 1;
    const cMinRaw = Math.min(...counts);
    const cMaxRaw = Math.max(...counts);
    const cSpan = cMaxRaw - cMinRaw || Math.max(1, Math.abs(cMaxRaw) * 0.05);
    const pad = cSpan * 0.08;
    const cMin = cMinRaw - pad;
    const cMax = cMaxRaw + pad;

    // x 按真实时间间隔线性映射，y 按粉丝数映射
    const x = (t) => M.left + ((t - tMin) / tSpan) * innerW;
    const y = (c) => M.top + (1 - (c - cMin) / (cMax - cMin)) * innerH;

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', '粉丝数历史趋势折线图');

    const makeText = (content, cx, cy, anchor, extra) => {
        const el = document.createElementNS(NS, 'text');
        el.setAttribute('x', cx);
        el.setAttribute('y', cy);
        el.setAttribute('text-anchor', anchor);
        el.textContent = content;
        if (extra) for (const k in extra) el.setAttribute(k, extra[k]);
        return el;
    };

    // 横向网格线 + y 轴刻度标签
    const yTicks = 4;
    for (let i = 0; i <= yTicks; i++) {
        const value = cMin + ((cMax - cMin) * i) / yTicks;
        const yy = y(value);
        const line = document.createElementNS(NS, 'line');
        line.setAttribute('x1', M.left);
        line.setAttribute('y1', yy);
        line.setAttribute('x2', W - M.right);
        line.setAttribute('y2', yy);
        line.setAttribute('class', 'chart-grid');
        svg.appendChild(line);
        svg.appendChild(makeText(formatChartCompact(value), M.left - 8, yy + 4, 'end'));
    }

    // 底部轴线 + x 轴时间刻度（按真实时间均匀取点）
    const axis = document.createElementNS(NS, 'line');
    axis.setAttribute('x1', M.left);
    axis.setAttribute('y1', y(cMin));
    axis.setAttribute('x2', W - M.right);
    axis.setAttribute('y2', y(cMin));
    axis.setAttribute('class', 'chart-axis');
    svg.appendChild(axis);

    const xTicks = 5;
    for (let i = 0; i < xTicks; i++) {
        const t = tMin + (tSpan * i) / (xTicks - 1);
        const xx = x(t);
        svg.appendChild(makeText(formatChartTime(t), xx, y(cMin) + 18, 'middle'));
    }

    // 折线
    const path = document.createElementNS(NS, 'path');
    const d = data
        .map((p, i) => `${i === 0 ? 'M' : 'L'}${x(p.t).toFixed(1)},${y(p.c).toFixed(1)}`)
        .join('');
    path.setAttribute('d', d);
    path.setAttribute('class', 'chart-line');
    svg.appendChild(path);

    // 数据点（点数多时省略，避免遮挡）
    if (data.length <= 120) {
        for (const p of data) {
            const dot = document.createElementNS(NS, 'circle');
            dot.setAttribute('cx', x(p.t));
            dot.setAttribute('cy', y(p.c));
            dot.setAttribute('r', 2.5);
            dot.setAttribute('class', 'chart-dot');
            svg.appendChild(dot);
        }
    }

    // 高亮最后一个点并标注最新粉丝数
    const last = data[data.length - 1];
    const lastDot = document.createElementNS(NS, 'circle');
    lastDot.setAttribute('cx', x(last.t));
    lastDot.setAttribute('cy', y(last.c));
    lastDot.setAttribute('r', 4.5);
    lastDot.setAttribute('class', 'chart-dot-last');
    svg.appendChild(lastDot);
    svg.appendChild(
        makeText(
            formatChartCompact(last.c),
            x(last.t) - 8,
            y(last.c) - 8,
            'end',
            { fill: '#ff5e7c', 'font-weight': '600' }
        )
    );

    container.replaceChildren(svg);

    // ===== 悬停：吸附最近采样点，竖直参考线 + 圆点标记，弹窗跟随鼠标 =====
    const tooltip = document.createElement('div');
    tooltip.className = 'chart-tooltip';
    container.appendChild(tooltip);

    const hover = document.createElementNS(NS, 'g');
    hover.setAttribute('class', 'chart-hover');
    const guide = document.createElementNS(NS, 'line');
    guide.setAttribute('class', 'chart-guide');
    const hoverDot = document.createElementNS(NS, 'circle');
    hoverDot.setAttribute('r', 4.5);
    hoverDot.setAttribute('class', 'chart-hover-dot');
    hover.appendChild(guide);
    hover.appendChild(hoverDot);
    svg.appendChild(hover);

    // 二分查找时间轴上与目标最接近的采样点下标（数据按时间升序）
    const closestIndex = (target) => {
        let lo = 0;
        let hi = times.length - 1;
        if (target <= times[lo]) return lo;
        if (target >= times[hi]) return hi;
        while (lo + 1 < hi) {
            const mid = (lo + hi) >> 1;
            if (times[mid] <= target) lo = mid;
            else hi = mid;
        }
        return target - times[lo] <= times[hi] - target ? lo : hi;
    };

    // 竖屏手机 CSS 将 svg 旋转 90°（时间轴视觉上变为纵向）时的几何判定
    const isRotatedChart = () =>
        window.matchMedia &&
        window.matchMedia('(max-width: 640px) and (orientation: portrait)').matches;

    // 屏幕坐标 -> 最近采样点。
    // 未旋转：沿 svg 可视宽度（X）采样；旋转后：时间轴沿可视高度（Y）排列，
    // svg.getBoundingClientRect() 返回的是旋转后的外接框，采样 Y 即等价于原时间轴 X。
    const sampleFromPointer = (clientX, clientY) => {
        const sRect = svg.getBoundingClientRect();
        const rotated = isRotatedChart();
        const frac = rotated
            ? (clientY - sRect.top) / sRect.height
            : (clientX - sRect.left) / sRect.width;
        const vx = Math.min(1, Math.max(0, frac)) * W;
        const target = tMin + ((vx - M.left) / innerW) * tSpan;
        return data[closestIndex(target)];
    };

    // 在参考线/标记点/弹窗上展示某个采样点（参考线与标记绘制在 svg 内部，
    // 旋转模式下会随图表一起旋转到正确朝向；弹窗按容器坐标跟随手指/鼠标）。
    const showOverlayAt = (clientX, clientY) => {
        const p = sampleFromPointer(clientX, clientY);
        const px = x(p.t);
        const py = y(p.c);

        guide.setAttribute('x1', px);
        guide.setAttribute('y1', y(cMin));
        guide.setAttribute('x2', px);
        guide.setAttribute('y2', y(cMax));
        hoverDot.setAttribute('cx', px);
        hoverDot.setAttribute('cy', py);
        hover.style.opacity = 1;

        tooltip.innerHTML = `<strong>${formatChartFullTime(p.t)}</strong><br>${p.c.toLocaleString()} 粉丝`;

        const cRect = container.getBoundingClientRect();
        tooltip.style.display = 'block';
        let left = clientX - cRect.left + 16;
        let top = clientY - cRect.top - tooltip.offsetHeight - 12;
        const maxLeft = cRect.width - tooltip.offsetWidth - 4;
        if (left > maxLeft) left = clientX - cRect.left - tooltip.offsetWidth - 16;
        if (left < 4) left = 4;
        if (top < 4) top = clientY - cRect.top + 16;
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    };

    const hideOverlay = () => {
        hover.style.opacity = 0;
        tooltip.style.display = 'none';
    };

    // 桌面：鼠标悬停跟随
    svg.addEventListener('pointermove', (ev) => {
        if (ev.pointerType !== 'mouse' && ev.pointerType !== 'pen') return;
        showOverlayAt(ev.clientX, ev.clientY);
    });
    svg.addEventListener('pointerleave', () => {
        hideOverlay();
    });

    // 移动端：点按图表显示该点详情（保留旋转几何，时间轴方向为屏幕纵向）。
    // 不拦截默认手势，页面滚动不受影响；点击图表外部自动隐藏。
    svg.addEventListener('click', (ev) => {
        showOverlayAt(ev.clientX, ev.clientY);
    });
    document.addEventListener('click', (ev) => {
        if (!container.contains(ev.target)) hideOverlay();
    });

    // 旋转/横竖屏切换后旧弹窗位置失效，自动隐藏
    window.addEventListener('resize', hideOverlay);
}

drawHistoryChart();

// ===== 历史快照：中间折叠块动态加载 =====
// 服务端只渲染首尾各 50 条卡片；中间每个区间以占位行表示（主文字为起止序号，
// 小字为起止时间）。点击后依据页面内联的 HISTORY_DATA（仅 {t, c}，日期用
// 已有 formatChartFullTime 由 ts 渲染，前后端分离）动态渲染，可再次收起。
function buildExpandableHistory() {
    const grid = document.getElementById('historyCards');
    if (!grid) return;
    const data = typeof HISTORY_DATA !== 'undefined' ? HISTORY_DATA : [];

    // 与服务端 card_html 一致：日期由 ts 格式化（YYYY-MM-DD HH:MM，与服务端 date 文本同精度）/ count / 相对上一条增减量
    const cardHtml = (i) => {
        const p = data[i];
        const prev = i > 0 ? data[i - 1].c : null;
        let changeStr = '—';
        let changeClass = '';
        if (prev !== null) {
            const dlt = p.c - prev;
            changeStr = (dlt >= 0 ? '+' : '') + dlt; // 与 Python 的 {:+.0f} 一致：0 -> '+0'
            changeClass = dlt > 0 ? 'positive' : 'negative';
        }
        return `<div class="history-card"><div class="card-date">${formatChartFullTime(p.t)}</div>` +
               `<div class="card-count">${p.c}</div>` +
               `<div class="card-change ${changeClass}">${changeStr}</div></div>`;
    };

    const buildChunk = (start, count) => {
        const end = Math.min(start + count, data.length);
        let html = '';
        for (let i = start; i < end; i++) html += cardHtml(i);
        return html;
    };

    // 主文字用起止序号（1-based），与服务端占位行文案一致；收起态联动切换
    const rangeText = (row) => {
        const start = parseInt(row.dataset.start, 10);
        const count = parseInt(row.dataset.count, 10);
        return `${start + 1} ~ ${start + count}`;
    };

    const setLabel = (row, open) => {
        const label = row.querySelector('.history-expand-label');
        if (label) label.textContent = open ? `收起 ${rangeText(row)} 项目` : `展开 ${rangeText(row)} 项目`;
        row.setAttribute('aria-expanded', open ? 'true' : 'false');
    };

    const toggle = (row) => {
        const start = parseInt(row.dataset.start, 10);
        const count = parseInt(row.dataset.count, 10);
        if (!row._anchor) {
            const anchor = document.createElement('span');
            anchor.className = 'history-anchor'; // display:none 的定位标记
            row.before(anchor);
            row._anchor = anchor;
        }
        const anchor = row._anchor;
        const opening = row.getAttribute('aria-expanded') !== 'true';

        if (opening) {
            // 仅首次点击时构建该块 HTML，之后复用缓存字符串
            if (!row._html) row._html = buildChunk(start, count);
            const wrap = document.createElement('div');
            wrap.innerHTML = row._html;
            while (wrap.firstChild) anchor.parentNode.insertBefore(wrap.firstChild, row);
            setLabel(row, true);
        } else {
            // 收起：移除 anchor 与 row 之间的全部动态卡片
            while (anchor.nextSibling && anchor.nextSibling !== row) {
                anchor.parentNode.removeChild(anchor.nextSibling);
            }
            setLabel(row, false);
        }
    };

    grid.addEventListener('click', (ev) => {
        const row = ev.target.closest('.history-expand');
        if (row) toggle(row);
    });
    grid.addEventListener('keydown', (ev) => {
        const row = ev.target.closest('.history-expand');
        if (row && (ev.key === 'Enter' || ev.key === ' ')) {
            ev.preventDefault();
            toggle(row);
        }
    });
}

buildExpandableHistory();
