// 请将 UID 替换为你的 B站 UID
const API_URL = `https://api.codetabs.com/v1/proxy/?quest=https://api.bilibili.com/x/relation/stat?vmid=${BILIBILI_UID}`;

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
    try {
        // 添加一个包含常见浏览器请求头的对象
        const response = await fetch(API_URL + '&time=' + Date.now());
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
        } else {
            console.error('API error:', data);
        }
    } catch (error) {
        console.error('Fetch failed:', error);
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

function formatChartCompact(n) {
    if (n >= 1000000) return `${(n / 1000000).toFixed(1).replace(/\.0$/, '')}M`;
    if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`;
    return String(Math.round(n));
}

function drawHistoryChart() {
    const container = document.getElementById('historyChart');
    if (!container) return;
    const data = window.HISTORY_DATA || [];
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
            x(last.t) + 8,
            y(last.c) - 8,
            'start',
            { fill: '#ff5e7c', 'font-weight': '600' }
        )
    );

    container.replaceChildren(svg);
}

drawHistoryChart();
