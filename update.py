import os
import json
import shutil
import random
import requests
from datetime import datetime
from zoneinfo import ZoneInfo  # 在文件顶部导入

# ========== 配置 ==========
DATA_FILE = 'data.json'
TEMPLATE_FILE = 'template.html'
PUBLIC_DIR = 'public'   # 静态资源目录（index.css / index.js）
BUILD_DIR = 'build'     # 生成的站点目录

TZ = ZoneInfo('Asia/Shanghai')      # 统一使用北京时间
RANDOM_FETCH_PROB = 1 / 12          # 非赞助商每次运行触发抓取的概率（保持原有逻辑）
RECOMMEND_COUNT = 3                 # 推荐区普通 UP 按钮数量


def fetch_fans_count(uid):
    api_url = f'https://api.bilibili.com/x/relation/stat?vmid={uid}'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        data = resp.json()
        if data['code'] == 0:
            return data['data']['follower']
        else:
            print(f"API error: {data}")
            return None
    except Exception as e:
        print(f"Error fetching fans: {e}")
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
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
        # 为缺少 ts 的旧记录补算时间戳（内存中回填，随 save_history 落盘）
        for records in history.values():
            for entry in records:
                _entry_ts(entry)
        return history
    return {}


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


def render_up_page(template, history, ups, up):
    """渲染单个 UP 详情页到 build/；无任何数据可渲染时返回 False。

    抓取触发概率保持原有逻辑；未触发（或抓取失败但有历史记录）时，
    使用最近一次记录值渲染，保证所有 UP 页面每轮都会重新生成。
    """
    uid = up['uid']
    data = up['data']
    is_sponsor = data.get('weight', 0) > 0
    records = history.get(uid, [])

    if is_sponsor or not records or random.random() < RANDOM_FETCH_PROB:
        fetched = fetch_fans_count(uid)
        if fetched is None:
            print(f"Failed to fetch fans count of {uid}.")
            if not records:
                print(f"No data to render {uid}, skipped.")
                return False
            # 抓取失败但有历史记录：回退最近一次记录值渲染，不新增记录
        else:
            now = datetime.now(TZ)
            records.append({
                'date': now.strftime("%Y-%m-%d %H:%M"),
                'count': fetched,
                'ts': int(now.timestamp()),
            })
            history[uid] = records

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


def main():
    # 复制静态资源到生成目录，再写入生成的 HTML
    shutil.copytree(PUBLIC_DIR, BUILD_DIR, dirs_exist_ok=True)

    history = load_history()

    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        template = f.read()
    with open('index_template.html', 'r', encoding='utf-8') as f:
        index_template = f.read()

    print("Data loaded.")

    ups = collect_ups()
    sponsor_links = []
    more_ups_links = []

    for up in ups:
        uid = up['uid']
        is_sponsor = up['data'].get('weight', 0) > 0

        # 每轮重新渲染全部 UP 页（数据源：本轮抓取或最近一次记录）
        if render_up_page(template, history, ups, up):
            print(f"Stored {uid}.")

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

    with open(os.path.join(BUILD_DIR, 'index.html'), 'w', encoding='utf-8') as f:
        index_html_content = index_template.replace('{{ups-sponsor}}', ''.join(sponsor_links))
        index_html_content = index_html_content.replace('{{ups-more}}', ''.join(more_ups_links))
        f.write(index_html_content)
        print("Stored index.")

    print("Update completed.")


if __name__ == '__main__':
    main()
