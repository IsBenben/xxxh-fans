import os
import json
import requests
from datetime import datetime
import sys
from zoneinfo import ZoneInfo  # 在文件顶部导入

# ========== 配置 ==========
DATA_FILE = 'data.json'
TEMPLATE_FILE = 'template.html'
TOTAL_GOAL = 11000         # 进度条总目标

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
    os.makedirs('dist', exist_ok=True)
    
    history = load_history()
    
    with open(TEMPLATE_FILE, 'r', encoding='utf-8') as f:
        template = f.read()
    
    for uid in os.listdir('ups'):
        with open(os.path.join('ups', uid), 'r', encoding='utf-8') as f:
            data = json.loads(f.readline())
            up_description = f.read()
        
        uid = uid.removesuffix('.txt')
        current_fans = fetch_fans_count(uid)
        if current_fans is None:
            print(f"Failed to fetch fans count of {uid}.")
            break
        
        now = datetime.now(ZoneInfo('Asia/Shanghai')).strftime("%Y-%m-%d %H:%M")
        history.setdefault(uid, []).append({"date": now, "count": current_fans})

        progress_percent = (current_fans / TOTAL_GOAL) * 100
        cards_html = generate_history_cards(history[uid])

        html_content = template.replace('{{fans_count}}', str(current_fans))
        html_content = html_content.replace('{{progress_width}}', f"{progress_percent:.2f}%")
        html_content = html_content.replace('{{history_cards}}', cards_html)
        html_content = html_content.replace('{{bilibili_uid}}', uid)
        html_content = html_content.replace('{{bilibili_name}}', data['name'])
        html_content = html_content.replace('{{total_progress}}', str(data['total_progress']))
        html_content = html_content.replace('{{up_description}}', up_description)
        
        for i, marker in enumerate(data['marker']):
            html_content = html_content.replace(f'{{{{marker_{i+1}_display}}}}', 'block')
            html_content = html_content.replace(f'{{{{marker_{i+1}_progress}}}}', str(marker['progress']))
            html_content = html_content.replace(f'{{{{marker_{i+1}_text}}}}', marker['text'])
        for i in range(3):
            html_content = html_content.replace(f'{{{{marker_{i+1}_display}}}}', 'none')
            html_content = html_content.replace(f'{{{{marker_{i+1}_progress}}}}', '0')
            html_content = html_content.replace(f'{{{{marker_{i+1}_text}}}}', '—')

        with open(f'dist/{uid}.html', 'w', encoding='utf-8') as f:
            f.write(html_content)
            print(f"Stored {uid}.")
            
    save_history(history)

    print("Update completed.")

if __name__ == '__main__':
    main()
