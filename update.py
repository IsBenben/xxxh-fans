import os
import json
import html
import shutil
import random
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo  # 在文件顶部导入
from xml.sax.saxutils import escape as xml_escape

# ========== 配置 ==========
DATA_FILE = 'data.json'
TEMPLATE_FILE = 'template.html'
PUBLIC_DIR = 'public'   # 静态资源目录（index.css / index.js）
BUILD_DIR = 'build'     # 生成的站点目录

TZ = ZoneInfo('Asia/Shanghai')      # 统一使用北京时间
RANDOM_FETCH_PROB = 1 / 10          # 非赞助商每次运行触发抓取的概率（保持原有逻辑）
RECOMMEND_COUNT = 3                 # 推荐区普通 UP 按钮数量

# 历史快照渲染策略：服务端默认只渲染首尾各 50 条，中间按每 50 条折叠为「展开 n 项目」
HISTORY_EDGE = 50                   # 首/尾直接渲染的卡片数
HISTORY_CHUNK = 50                  # 中间每个折叠块的条数

# ========== SEO ==========
SITE_URL = 'https://isbenben.github.io/xxxh-fans/'   # 站点对外地址（canonical/OG/sitemap）
SITE_NAME = 'Bilibili 实时大屏'
INDEX_TITLE = 'Bilibili 实时大屏 - B站UP主实时粉丝数与历史趋势'
INDEX_DESCRIPTION = ('Bilibili 实时大屏：汇总多位B站UP主的实时粉丝数、里程碑进度'
                     '与历史数据趋势，直观展示，便于关注与追踪。')


def log(msg):
    """带北京时间前缀的统一日志输出。"""
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")


def esc_html(value):
    """HTML 转义，用于注入模板属性与文本节点。"""
    return html.escape(str(value), quote=True)


def json_ld_script(obj):
    """将对象序列化为可安全嵌入 <script> 的 JSON-LD 文本。"""
    text = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    return text.replace('</', '<\\/')


def fetch_fans_count(uid):
    api_url = f'https://api.bilibili.com/x/relation/stat?vmid={uid}'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        data = resp.json()
        if data['code'] == 0:
            return data['data']['follower']
        else:
            log(f"  API error for uid={uid}: {data}")
            return None
    except Exception as e:
        log(f"  Request error for uid={uid}: {e}")
        return None


def _entry_ts(entry):
    """取记录时间戳；旧数据缺少 ts 时按 date（Asia/Shanghai，HH:MM 秒取 0）补算并回填。"""
    ts = entry.get('ts')
    if ts is None:
        try:
            dt = datetime.strptime(entry['date'], "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
            ts = int(dt.timestamp())
        except (KeyError, ValueError, TypeError):
            ts = None
        entry['ts'] = ts
    return ts


def load_history():
    history = {}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
    n_ups = len(history)
    n_records = sum(len(v) for v in history.values())
    missing = 0
    for records in history.values():
        for entry in records:
            if entry.get('ts') is None:
                missing += 1
                # 为缺少 ts 的旧记录补算时间戳（内存中回填，随 save_history 落盘）
                _entry_ts(entry)
    if n_ups == 0:
        log("History loaded: empty (data.json 不存在或无记录)")
    else:
        detail = f"{n_ups} UP(s), {n_records} record(s)"
        if missing:
            detail += f", {missing} old record(s) backfilled with ts"
        log(f"History loaded: {detail}")
    return history


def save_history(history):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def generate_history_cards(records):
    """生成历史卡片HTML。

    渲染策略：数据 <= 首尾各50条时全部直出；否则服务端只渲染
    最旧的前50条 + 最新的后50条，中间区间按每 HISTORY_CHUNK(50) 条
    折叠为一个占位行。占位行主文字为起止序号「展开 a ~ b 项目」，
    小字为该块首尾记录的起止时间，由前端 JS 依据 HISTORY_DATA
    （仅 {t, c}，日期由 ts 格式化）动态加载/收起。

    输出紧凑无前导空白/换行：插入 .cards-grid 后不会产生空白文本
    形成的匿名网格格子。
    """
    n = len(records)
    # 与卡片格式一一对应的展示信息（跨块边界的增减量按前一条真实数据计算）
    infos = []
    for i, item in enumerate(records):
        count = item['count']
        date_str = item['date']
        if i == 0:
            change_str = '—'
            change_class = ''
        else:
            dlt = count - records[i - 1]['count']
            change_str = f"{dlt:+d}"
            change_class = 'positive' if dlt > 0 else 'negative'
        infos.append((date_str, count, change_str, change_class))

    def card_html(idx):
        date_str, count, change_str, change_class = infos[idx]
        return ('<div class="history-card">'
                f'<div class="card-date">{date_str}</div>'
                f'<div class="card-count">{count}</div>'
                f'<div class="card-change {change_class}">{change_str}</div>'
                '</div>')

    def expand_row(block_start, block_end):
        count = block_end - block_start
        start_date = infos[block_start][0]
        end_date = infos[block_end - 1][0]
        nums = f'{block_start + 1} ~ {block_start + count}'
        return ('<div class="history-expand" role="button" tabindex="0" '
                f'aria-expanded="false" data-start="{block_start}" data-count="{count}">'
                f'<span class="history-expand-label">展开 {nums} 项目</span>'
                f'<span class="history-expand-range">{start_date} ~ {end_date}</span>'
                '</div>')

    if n <= HISTORY_EDGE * 2:
        return ''.join(card_html(i) for i in range(n))

    head_end = HISTORY_EDGE                    # 前50：下标 [0, head_end)
    tail_start = n - HISTORY_EDGE              # 后50：下标 [tail_start, n)
    parts = [''.join(card_html(i) for i in range(head_end))]

    # 中间块：[head_end, tail_start) 内每 50 条一个占位行
    for block_start in range(head_end, tail_start, HISTORY_CHUNK):
        block_end = min(block_start + HISTORY_CHUNK, tail_start)
        parts.append(expand_row(block_start, block_end))

    parts.append(''.join(card_html(i) for i in range(tail_start, n)))
    return ''.join(parts)


def collect_ups():
    """收集全部 UP 配置（.txt 首行 JSON + 其余为描述 HTML），供渲染与推荐使用。"""
    ups = []
    for dirpath, _dirnames, filenames in os.walk('ups'):
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.loads(f.readline())
                description = f.read()
            ups.append({
                'uid': filename.removesuffix('.txt'),
                'data': data,
                'description': description,
            })
    return ups


def build_button(up, rainbow=False):
    uid = up['uid']
    cls = 'follow-button' + (' rainbow-button' if rainbow else '')
    return f'<a href="./{uid}.html" target="_blank" class="{cls}">{up["data"]["name"]}</a>'


def build_recommendations(ups, current_uid):
    """推荐区按钮 HTML：weight 加权随机 1 个赞助商 + 随机 N 个普通 UP（均排除当前页）。"""
    sponsors = [u for u in ups if u['data'].get('weight', 0) > 0 and u['uid'] != current_uid]
    others = [u for u in ups if u['data'].get('weight', 0) <= 0 and u['uid'] != current_uid]

    buttons = []
    if sponsors:
        weights = [max(int(u['data'].get('weight', 0)), 1) for u in sponsors]
        buttons.append(build_button(random.choices(sponsors, weights=weights, k=1)[0], rainbow=True))
    if others:
        for up in random.sample(others, min(RECOMMEND_COUNT, len(others))):
            buttons.append(build_button(up))
    return '\n'.join(buttons)


def up_page_seo(up, current_fans):
    """单个 UP 详情页的 SEO 数据：title / description / canonical / JSON-LD。"""
    uid = up['uid']
    name = up['data']['name']
    total = up['data']['total_progress']
    title = f"{name}粉丝数_历史趋势 - {SITE_NAME}"
    description = (f"{name} 是B站UP主，当前粉丝数 {current_fans}（目标 {total}）。"
                   f"可在 {SITE_NAME} 查看实时粉丝数、历史数据与里程碑进度。")
    canonical = f"{SITE_URL}{uid}.html"
    json_ld = {
        '@context': 'https://schema.org',
        '@type': 'ProfilePage',
        'name': name,
        'url': canonical,
        'description': description,
        'mainEntity': {
            '@type': 'Person',
            'name': name,
            'url': f'https://space.bilibili.com/{uid}',
            'interactionStatistic': {
                '@type': 'InteractionCounter',
                'interactionType': 'https://schema.org/FollowAction',
                'userInteractionCount': int(current_fans),
            },
        },
    }
    return title, description, canonical, json_ld


def index_seo(ups):
    """首页 SEO 数据：JSON-LD 为 WebSite + 全部 UP 的 ItemList。"""
    item_list = [
        {
            '@type': 'ListItem',
            'position': i + 1,
            'name': u['data']['name'],
            'url': f"{SITE_URL}{u['uid']}.html",
        }
        for i, u in enumerate(ups)
    ]
    json_ld = {
        '@context': 'https://schema.org',
        '@graph': [
            {
                '@type': 'WebSite',
                'name': SITE_NAME,
                'url': SITE_URL,
                'description': INDEX_DESCRIPTION,
            },
            {'@type': 'ItemList', 'name': '收录UP主', 'itemListElement': item_list},
        ],
    }
    return INDEX_TITLE, INDEX_DESCRIPTION, SITE_URL, json_ld


def render_up_page(template, history, ups, up, offline=False):
    """渲染单个 UP 详情页到 build/；无任何数据可渲染时返回 False。

    非离线模式：抓取触发概率保持原有逻辑，未触发（或抓取失败但有历史记录）时
    使用最近一次记录值渲染，保证所有 UP 页面每轮都会重新生成。
    离线模式（offline=True）：不发起任何网络请求，一律用 data.json 历史数据渲染。
    """
    uid = up['uid']
    data = up['data']
    name = data['name']
    is_sponsor = data.get('weight', 0) > 0
    records = history.get(uid, [])
    tag = f"{uid} ({name})"

    if not offline and (is_sponsor or not records or random.random() < RANDOM_FETCH_PROB):
        source = 'sponsor' if is_sponsor else ('no history' if not records else 'random fetch')
        log(f"  [{tag}] fetching ... (reason: {source})")
        fetched = fetch_fans_count(uid)
        if fetched is None:
            log(f"  [{tag}] fetch FAILED (API/network error)")
            if not records:
                log(f"  [{tag}] no cached data -> page SKIPPED")
                return False
            # 抓取失败但有历史记录：回退最近一次记录值渲染，不新增记录
            log(f"  [{tag}] fallback to last cached value")
        else:
            prev = records[-1]['count'] if records else None
            now = datetime.now(TZ)
            records.append({
                'date': now.strftime("%Y-%m-%d %H:%M"),
                'count': fetched,
                'ts': int(now.timestamp()),
            })
            history[uid] = records
            if prev is None:
                log(f"  [{tag}] fetch OK: first record -> {fetched} fans")
            else:
                log(f"  [{tag}] fetch OK: {fetched} fans (prev {prev}, delta {fetched - prev:+d})")
    else:
        if offline and not records:
            log(f"  [{tag}] offline: no cached data -> page SKIPPED")
            return False
        if offline:
            log(f"  [{tag}] offline: render from cached history")
        else:
            log(f"  [{tag}] cached: not this round (random 1/{int(1 / RANDOM_FETCH_PROB)})")

    current_fans = records[-1]['count']

    progress_percent = (current_fans / data['total_progress']) * 100
    cards_html = generate_history_cards(records)

    # 历史图表数据：时间戳 + 粉丝数（时间不均匀，前端按真实时间定位）。
    # 前后端分离：不传日期文本，由前端依据 ts 用已有时间戳->日期函数渲染
    points = []
    for entry in records:
        ts = _entry_ts(entry)
        if ts is not None:
            points.append({'t': ts, 'c': entry['count']})
    history_data = json.dumps(points, ensure_ascii=False, separators=(',', ':'))

    # SEO：title / description / canonical / JSON-LD
    page_title, meta_description, canonical_url, json_ld = up_page_seo(up, current_fans)

    html_content = template
    html_content = html_content.replace('{{progress_width}}', f"{progress_percent:.2f}%")
    html_content = html_content.replace('{{history_cards}}', cards_html)
    html_content = html_content.replace('{{history_data}}', history_data)
    html_content = html_content.replace('{{recommend_buttons}}', build_recommendations(ups, uid))

    html_content = html_content.replace('{{page_title}}', esc_html(page_title))
    html_content = html_content.replace('{{meta_description}}', esc_html(meta_description))
    html_content = html_content.replace('{{canonical_url}}', esc_html(canonical_url))
    html_content = html_content.replace('{{json_ld}}', json_ld_script(json_ld))

    html_content = html_content.replace('{{total_progress}}', str(data['total_progress']))
    html_content = html_content.replace('{{up_description}}', up['description'])
    html_content = html_content.replace('{{fans_count}}', str(current_fans))
    html_content = html_content.replace('{{bilibili_uid}}', uid)
    html_content = html_content.replace('{{bilibili_name}}', esc_html(data['name']))

    if not is_sponsor:
        html_content = html_content.replace('约每小时更新', '每日更新1~2次')

    for i, marker in enumerate(data['marker']):
        html_content = html_content.replace(f'{{{{marker_{i+1}_display}}}}', 'block')
        html_content = html_content.replace(f'{{{{marker_{i+1}_progress}}}}', str(marker['progress']))
        html_content = html_content.replace(f'{{{{marker_{i+1}_text}}}}', marker['text'])
    for i in range(3):
        html_content = html_content.replace(f'{{{{marker_{i+1}_display}}}}', 'none')
        html_content = html_content.replace(f'{{{{marker_{i+1}_progress}}}}', '0')
        html_content = html_content.replace(f'{{{{marker_{i+1}_text}}}}', '—')

    with open(os.path.join(BUILD_DIR, f'{uid}.html'), 'w', encoding='utf-8') as f:
        f.write(html_content)
    return True


def main(offline=False):
    start = time.time()
    log("=" * 60)
    log("Bilibili 实时大屏 站点生成开始")
    log(f"Mode: {'OFFLINE（不发起任何网络请求）' if offline else 'online'}")
    log(f"Data file: {DATA_FILE} | Output dir: {BUILD_DIR} (assets from {PUBLIC_DIR})")

    # 复制静态资源到生成目录，再写入生成的 HTML
    shutil.copytree(PUBLIC_DIR, BUILD_DIR, dirs_exist_ok=True)
    log(f"Static assets copied: {PUBLIC_DIR}/ -> {BUILD_DIR}/")

    history = load_history()

    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        template = f.read()
    with open('index_template.html', 'r', encoding='utf-8') as f:
        index_template = f.read()
    log(f"Templates loaded: {TEMPLATE_FILE}, index_template.html")

    ups = collect_ups()
    sponsor_count = sum(1 for u in ups if u['data'].get('weight', 0) > 0)
    log(f"UP configs found: {len(ups)} total ({sponsor_count} sponsor, {len(ups) - sponsor_count} regular)")

    sponsor_links = []
    more_ups_links = []
    rendered = 0
    skipped = 0
    records_before = sum(len(v) for v in history.values())

    log("-" * 60)
    log("开始渲染各 UP 详情页 ...")
    for up in ups:
        uid = up['uid']
        is_sponsor = up['data'].get('weight', 0) > 0

        # 每轮重新渲染全部 UP 页（数据源：本轮抓取或最近一次记录）
        if render_up_page(template, history, ups, up, offline=offline):
            log(f"  page written: {BUILD_DIR}/{uid}.html")
            rendered += 1
        else:
            skipped += 1

        button_class = 'rainbow-button' if is_sponsor else ''
        button_list = sponsor_links if is_sponsor else more_ups_links
        button_list.append(f"""\
        <a
        href="./{uid}.html"
        target="_blank"
        class="follow-button {button_class}"
        >
        {up['data']['name']}
        </a>""")

    save_history(history)
    records_after = sum(len(v) for v in history.values())
    log(f"History saved to {DATA_FILE}")

    # 首页（含 SEO：title / description / canonical / JSON-LD）
    idx_title, idx_desc, idx_canonical, idx_json_ld = index_seo(ups)
    index_html_content = index_template
    index_html_content = index_html_content.replace('{{ups-sponsor}}', ''.join(sponsor_links))
    index_html_content = index_html_content.replace('{{ups-more}}', ''.join(more_ups_links))
    index_html_content = index_html_content.replace('{{page_title}}', esc_html(idx_title))
    index_html_content = index_html_content.replace('{{meta_description}}', esc_html(idx_desc))
    index_html_content = index_html_content.replace('{{canonical_url}}', esc_html(idx_canonical))
    index_html_content = index_html_content.replace('{{json_ld}}', json_ld_script(idx_json_ld))
    with open(os.path.join(BUILD_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(index_html_content)
    log(f"Index page written: {BUILD_DIR}/index.html")

    # robots.txt + sitemap.xml（列出首页与所有有数据的 UP 页）
    base_url = SITE_URL if SITE_URL.endswith('/') else SITE_URL + '/'
    with open(os.path.join(BUILD_DIR, 'robots.txt'), 'w', encoding='utf-8') as f:
        f.write(f'User-agent: *\nAllow: /\nSitemap: {base_url}sitemap.xml\n')

    today = datetime.now(TZ).strftime('%Y-%m-%d')
    url_lines = [f'  <url><loc>{xml_escape(base_url)}</loc><lastmod>{today}</lastmod>'
                 f'<changefreq>hourly</changefreq><priority>1.0</priority></url>']
    for up in ups:
        uid = up['uid']
        if uid not in history or not history[uid]:
            continue
        lastmod = history[uid][-1]['date'].split(' ')[0]
        loc = xml_escape(f"{base_url}{uid}.html")
        url_lines.append(f'  <url><loc>{loc}</loc><lastmod>{lastmod}</lastmod>'
                         f'<changefreq>daily</changefreq><priority>0.8</priority></url>')
    with open(os.path.join(BUILD_DIR, 'sitemap.xml'), 'w', encoding='utf-8') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                + '\n'.join(url_lines) + '\n</urlset>\n')
    log(f"SEO files written: {BUILD_DIR}/robots.txt, {BUILD_DIR}/sitemap.xml ({len(url_lines)} URLs)")

    log("-" * 60)
    log(f"Summary: pages rendered={rendered}, skipped={skipped}")
    log(f"History records: {records_before} -> {records_after} ({records_after - records_before:+d} new this run)")
    log(f"Index buttons: {len(sponsor_links)} sponsor, {len(more_ups_links)} more")
    log(f"Elapsed: {time.time() - start:.2f}s")
    log("站点生成完成")
    log("=" * 60)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='生成 Bilibili 实时大屏静态站点')
    parser.add_argument(
        '--offline',
        action='store_true',
        help='离线模式：不触发任何网络请求，仅用 data.json 中的历史数据渲染所有页面',
    )
    args = parser.parse_args()
    main(offline=args.offline)
