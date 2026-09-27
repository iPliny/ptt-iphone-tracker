import requests
from bs4 import BeautifulSoup
import ollama
import json
import time
import random
import urllib3
import csv
import re
import os
import hashlib
from datetime import datetime

# 抑制 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.NotOpenSSLWarning)

# --- 基礎與狀態設定 ---
base_url = "https://www.ptt.cc"
current_url = "https://www.ptt.cc/bbs/MacShop/index.html"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

HISTORY_FILE = "scraping_history.json"
RAW_CSV_FILE = "macshop_raw_data.csv"

# 載入歷史抓取紀錄
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
        scrape_history = json.load(f)
else:
    scrape_history = {}

target_urls = []       
final_results = []     
pages_to_scrape = 2

def fetch_url_with_retry(url, headers, max_retries=3):
    """
    具備連線重置防禦機制的 HTTP 請求函數
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response
            else:
                print(f"[WARN] 伺服器回傳異常狀態碼：{response.status_code}")
                
        except requests.exceptions.ConnectionError as e:
            wait_time = 15 * (attempt + 1)
            print(f"[WARN] 觸發 PTT 防火牆 (連線被重置)。等待 {wait_time} 秒後進行第 {attempt + 1} 次重試...")
            time.sleep(wait_time)
            
        except Exception as e:
            print(f"[ERROR] 發生未知的網路錯誤：{e}")
            break
            
    return None

print("=" * 60)
print("[INFO] 啟動爬蟲任務：目標鎖定 PTT MacShop 版")
print("=" * 60)

# ==========================================
# 第一階段：自動翻頁與收集網址
# ==========================================
for page in range(pages_to_scrape):
    print(f"\n---> [SCAN] 正在掃描第 {page + 1} 頁 <---")
    
    response = fetch_url_with_retry(current_url, headers=headers)
    
    if response and response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        articles = soup.find_all("div", class_="r-ent")
        
        for article in articles:
            title_element = article.find("div", class_="title").find("a")
            if title_element:
                title = title_element.text.strip()
                title_lower = title.lower()
                
                print(f"[*] 發現貼文: {title}")
                
                if any(keyword in title for keyword in ["[販售]", "售出", "已售"]) and "iphone" in title_lower:
                    link = base_url + title_element["href"]
                    target_urls.append({"title": title, "link": link})
                    print(f"    [+] 鎖定目標：成功加入排程清單。")
        
        paging_div = soup.find("div", class_="btn-group btn-group-paging")
        prev_page_link = paging_div.find_all("a")[1]["href"]
        current_url = base_url + prev_page_link
        time.sleep(random.uniform(1, 2))
    else:
        print(f"[ERROR] 第 {page + 1} 頁連線失敗或達重試上限。")
        break

print(f"\n[INFO] 第一階段完成，共收集到 {len(target_urls)} 篇待處理文章。")
print("=" * 60)
print("[INFO] 執行狀態比對與 AI 深度解析...")
print("=" * 60)

# ==========================================
# 第二階段：Hash 比對、AI 萃取與業務邏輯清洗
# ==========================================
system_prompt = """
你是一個專業的台灣二手蘋果商品數據分析師。
請從以下的 PTT 交易文當中，精準萃取出「iPhone」的資訊，並嚴格以 JSON 格式回傳。
【萃取規則】：
1. model: iPhone 手機型號字串。注意：若文章「僅」販售配件或 Watch/iPad 等，請務必填 null。若是搭售，請專注萃取 iPhone 的型號。
2. storage: 容量字串
3. battery_health: 電池健康度數字 (不含百分比符號)。若無提及請填 null。
4. price: 價格數字。注意：若為搭售，請僅萃取 iPhone 的單機標價；若賣家標示為「不拆賣的總包價」，請填 null 以免干擾市場均價。
5. warranty: 保固狀態。若語意是開通後一年，則顯示「一年」。若內文提及具體保固期限，請嚴格過濾掉「保固內」、「保固至」、「到」與括號等冗餘中文字，僅保留純日期格式，以/作為日期標示（如：2026/3/25）。若明確標示過保，請填「無保固」。
6. notes: 其他備註重點摘要（請勿在此欄位提及配件是否全新）
7. is_brand_new: 布林值（true / false）。
   - 僅當 iPhone「機身本體」明確標示為全新未拆封、未開通、未啟動時，填 true。
   - 配件全新（例如：全新耳機、全新保護貼、全新保護殼）不算，一律填 false。
   - 已過保的手機絕對填 false。
   - 判斷依據必須來自文章內文，禁止推測或假設。

【特別注意】：
- 若文章販售商品為「手機殼」、「保護貼」、「充電線」、「配件」等，
  且完全未提及 iPhone 機身本體，model 與 price 一律填 null。
- 搭售情境：僅萃取 iPhone 機身的單獨標價，
  若賣家明確表示「不拆賣」，price 填 null。
- 判斷依據必須來自文章內文，禁止推測或假設。

請直接輸出 JSON，不要有任何其他文字。
"""

for idx, item in enumerate(target_urls):
    print(f"\n[{idx + 1}/{len(target_urls)}] 處理中: {item['title']}")
    
    post_response = fetch_url_with_retry(item['link'], headers=headers)
    
    if post_response and post_response.status_code == 200:
        post_soup = BeautifulSoup(post_response.text, "html.parser")
        main_content = post_soup.find(id="main-content")
        
        if main_content:
            content_text = main_content.text
            
            # --- 核心防禦：MD5 Hash 狀態比對 ---
            content_hash = hashlib.md5(content_text.encode('utf-8')).hexdigest()
            
            if item['link'] in scrape_history and scrape_history[item['link']] == content_hash:
                print("    [SKIP] 偵測到內文無任何變更，跳過 AI 解析，節省算力。")
                continue
            elif item['link'] in scrape_history:
                print("    [UPDATE] 偵測到文章已被編輯！啟動 AI 重新解析以記錄最新報價。")
            else:
                print("    [NEW] 全新文章，啟動 AI 解析。")

            try:
                ai_response = ollama.chat(
                    model='qwen2.5:32b',
                    messages=[
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': content_text}
                    ],
                    format='json'
                )                
                
                parsed_data = json.loads(ai_response['message']['content'])
                
                if not parsed_data.get("model") or str(parsed_data.get("model")).lower() == "null":
                    print("    [!] 捨棄：經 AI 判定為純配件或無效裝置交易")
                    scrape_history[item['link']] = content_hash
                    continue

                if not parsed_data.get("price"):
                    print("    [!] 捨棄：未偵測到明確的 iPhone 單機售價")
                    scrape_history[item['link']] = content_hash
                    continue

                current_time = datetime.now()
                parsed_data["scrape_timestamp"] = current_time.strftime("%Y-%m-%d %H:%M:%S")

                try:
                    url_parts = item['link'].split('/')[-1].split('.')
                    unix_timestamp = int(url_parts[1])
                    parsed_data["post_date"] = datetime.fromtimestamp(unix_timestamp).strftime('%Y-%m-%d')
                except:
                    parsed_data["post_date"] = "未知日期"
                
                storage_str = str(parsed_data.get("storage", "")).strip()
                num_match = re.search(r'\d+', storage_str)
                if num_match:
                    num = num_match.group()
                    parsed_data["storage"] = f"{num}TB" if 't' in storage_str.lower() else f"{num}GB"
                else:
                    parsed_data["storage"] = "未知"

                # ==========================================
                # 【修正】全新判定：完全交由 AI 的 is_brand_new 欄位決定
                # 不再使用關鍵字比對，避免「配件全新」污染判斷結果
                # ==========================================
                is_brand_new = "是" if parsed_data.get("is_brand_new") is True else "否"
                parsed_data["全新未拆封機"] = is_brand_new

                if is_brand_new == "是":
                    parsed_data["battery_health"] = 100
                    parsed_data["warranty"] = "1年"
                else:
                    warranty_text = str(parsed_data.get("warranty", ""))
                    notes_text = str(parsed_data.get("notes", ""))
                    combined_text = notes_text + warranty_text

                    if any(kw in combined_text for kw in ["已過保", "無保固"]):
                        parsed_data["warranty"] = "無保固"
                    else:
                        parsed_data["warranty"] = warranty_text if warranty_text else "未知"

                # 【修正】無塵室處理：剔除版規干擾，再行判定售出狀態
                clean_content = content_text.replace("售出後修改價格至不可視者水桶並劣退", "")
                sold_keywords = ["售出", "已售"]
                
                is_sold = "否"
                if any(kw in item['title'] for kw in sold_keywords):
                    is_sold = "是"
                    print("    [SYS] 偵測到標題包含已售/售出，標記為已售出。")
                elif any(kw in clean_content for kw in sold_keywords):
                    is_sold = "是"
                    print("    [SYS] 偵測到內文包含已售/售出，標記為已售出。")
                    
                parsed_data["是否已售出"] = is_sold
                parsed_data["source_url"] = item['link']

                # 清除不需要寫入 CSV 的中間欄位
                parsed_data.pop("is_brand_new", None)

                final_results.append(parsed_data)
                
                scrape_history[item['link']] = content_hash
                print("    [OK] 處理完成，已記錄最新狀態。")
                
            except Exception as e:
                print(f"    [ERR] 解析過程發生異常：{e}")
            
    else:
        print(f"    [ERROR] 無法取得文章網頁，跳過處理。")

    time.sleep(random.uniform(2, 4))

with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
    json.dump(scrape_history, f, ensure_ascii=False, indent=4)

print("=" * 60)
print(f"[INFO] 任務完結！本次共新增/更新 {len(final_results)} 筆交易數據。")

# ==========================================
# 第三階段：Raw Data 附加寫入 (Append Mode)
# ==========================================
if final_results:
    fieldnames = [
        "scrape_timestamp", "post_date", "model", "storage", "全新未拆封機", 
        "battery_health", "price", "warranty", "是否已售出", "notes", "source_url"
    ]
    
    file_exists = os.path.isfile(RAW_CSV_FILE)
    
    with open(RAW_CSV_FILE, 'a', newline='', encoding='utf-8-sig') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=fieldnames, extrasaction='ignore')
        
        if not file_exists:
            dict_writer.writeheader()
            
        dict_writer.writerows(final_results)
        
    print(f"[SUCCESS] Raw Data 已成功附加至檔案：{RAW_CSV_FILE}")
else:
    print("[INFO] 本次執行無任何新資料或更新，CSV 檔案維持原樣。")
