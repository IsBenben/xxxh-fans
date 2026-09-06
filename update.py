import os
import json
import shutil
import random
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo  # 在文件顶部导入

# ========== 配置 ==========
DATA_FILE = 'data.json'
TEMPLATE_FILE = 'template.html'
PUBLIC_DIR = 'public'   # 静态资源目录（index.css / index.js）
BUILD_DIR = 'build'     # 生成的站点目录

TZ = ZoneInfo('Asia/Shanghai')      # 统一使用北京时间
RANDOM_FETCH_PROB = 1 / 10          # 非赞助商每次运行触发抓取的概率（保持原有逻辑）
RECOMMEND_COUNT = 3                 # 推荐区普通 UP 按钮数量


def log(msg):
    """带北京时间前缀的统一日志输出。"""
    now = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {msg}")


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
    """生成历史卡片HTML"""
    cards = []
    for i, item in enumerate(records):
        count = item['count']
        date_str = item['date']
        if i == 0:
            change_str = '—'
            change_class = ''
        else:
            prev_count = records[i - 1]['count']
            change = count - prev_count
            change_str = f"{change:+d}"
            change_class = 'positive' if change > 0 else 'negative'
        card = f"""\
        <div class="history-card">
          <div class="card-date">{date_str}</div>
          <div class="card-count">{count}</div>
          <div class="card-change {change_class}">{change_str}</div>
        </div>"""
        cards.append(card)
    return ''.join(cards)


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

    # 历史图表数据：时间戳 + 粉丝数（时间不均匀，前端按真实时间定位）
    points = []
    for entry in records:
        ts = _entry_ts(entry)
        if ts is not None:
            points.append({'t': ts, 'c': entry['count']})
    history_data = json.dumps(points, ensure_ascii=False, separators=(',', ':'))

    html_content = template
    html_content = html_content.replace('{{progress_width}}', f"{progress_percent:.2f}%")
    html_content = html_content.replace('{{history_cards}}', cards_html)
    html_content = html_content.replace('{{history_data}}', history_data)
    html_content = html_content.replace('{{recommend_buttons}}', build_recommendations(ups, uid))

    html_content = html_content.replace('{{total_progress}}', str(data['total_progress']))
    html_content = html_content.replace('{{up_description}}', up['description'])
    html_content = html_content.replace('{{fans_count}}', str(current_fans))
    html_content = html_content.replace('{{bilibili_uid}}', uid)
    html_content = html_content.replace('{{bilibili_name}}', data['name'])

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

    with open(os.path.join(BUILD_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        index_html_content = index_template.replace('{{ups-sponsor}}', ''.join(sponsor_links))
        index_html_content = index_html_content.replace('{{ups-more}}', ''.join(more_ups_links))
        f.write(index_html_content)
    log(f"Index page written: {BUILD_DIR}/index.html")

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
