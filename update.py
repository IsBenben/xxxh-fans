import os
import json
import requests
from datetime import datetime
import sys
from zoneinfo import ZoneInfo  # 在文件顶部导入

# ========== 配置 ==========
UID = os.environ.get('BILIBILI_UID', '3546867929451208')  # 请替换为真实UID，或通过 Secrets 传入
API_URL = f'https://api.bilibili.com/x/relation/stat?vmid={UID}'
DATA_FILE = 'data.json'
TEMPLATE_FILE = 'template.html'
OUTPUT_FILE = 'index.html'
MAX_HISTORY = 1000000000
TOTAL_GOAL = 11000         # 进度条总目标

def fetch_fans_count():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        resp = requests.get(API_URL, headers=headers, timeout=10)
        data = resp.json()
        if data['code'] == 0:
            return data['data']['follower']
        else:
            print(f"API error: {data}")
            return None
    except Exception as e:
        print(f"Error fetching fans: {e}")
        return None

def load_history():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_history(history):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def generate_history_cards(history):
    """生成历史卡片HTML"""
    cards = []
    for i, item in enumerate(history):
        count = item['count']
        date_str = item['date']
        if i == 0:
            change_str = '—'
            change_class = ''
        else:
            prev_count = history[i-1]['count']
            change = count - prev_count
            change_str = f"{change:+d}"
            change_class = 'positive' if change > 0 else 'negative'
        card = f"""
        <div class="history-card">
            <div class="card-date">{date_str}</div>
            <div class="card-count">{count}</div>
            <div class="card-change {change_class}">{change_str}</div>
        </div>
        """
        cards.append(card)
    return ''.join(cards)

def main():
    current_fans = fetch_fans_count()
    if current_fans is None:
        print("Failed to fetch fans count. Exiting.")
        sys.exit(1)

    history = load_history()
    now = datetime.now(ZoneInfo('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M")
    history.append({"date": now, "count": current_fans})

    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    save_history(history)

    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        template = f.read()

    progress_percent = (current_fans / TOTAL_GOAL) * 100
    cards_html = generate_history_cards(history)

    html_content = template.replace('{{fans_count}}', str(current_fans))
    html_content = html_content.replace('{{progress_width}}', f"{progress_percent:.2f}%")
    html_content = html_content.replace('{{history_cards}}', cards_html)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print("Update completed.")

if __name__ == '__main__':
    main()
