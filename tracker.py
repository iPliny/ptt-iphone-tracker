"""
PTT MacShop iPhone 二手機成交追蹤 v2

v1 的問題：每次只看最新 2 頁，文章一旦被擠出前 2 頁就再也不會被回訪，
而賣家通常是「幾天後」才把標題改成已售出，所以成交狀態永遠抓不到。

v2 的流程（每次執行都做完這四步）：
  1. 掃描：往回翻頁，直到文章時間早於 --days 天前（上限 --max-pages 頁）。
  2. 萃取：新文章、或「本文」有被編輯（推文不算）的文章才送 Ollama 解析。
  3. 回訪：所有仍在售、且發文在 --track-days 天內的文章逐篇重新打開，
     只用標題/本文關鍵字判斷是否已售出或被刪除（不耗 LLM 算力）。
  4. 彙整：輸出 data/ 底下的 listings.csv（每篇文章一列、最新狀態）、events.csv（變動紀錄）、
     market_summary.csv（各型號行情）。

用法：
  python tracker.py                 # 完整執行
  python tracker.py --no-llm        # 只回訪既有文章、更新成交狀態（不需開 Ollama）
  python tracker.py --report-only   # 只重算行情彙整
  python tracker.py --migrate data/macshop_raw_data_v1.csv   # 把 v1 的 CSV 匯入成 listings.csv
"""

import argparse
import csv
import hashlib
import json
import os
import random
import re
import statistics
import time
from datetime import datetime, timedelta

import requests
import urllib3
from bs4 import BeautifulSoup

try:
    urllib3.disable_warnings(urllib3.exceptions.NotOpenSSLWarning)
except AttributeError:
    pass

BASE_URL = "https://www.ptt.cc"
INDEX_URL = BASE_URL + "/bbs/MacShop/index.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
OLLAMA_MODEL = "qwen2.5:32b"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
LISTINGS_FILE = os.path.join(DATA_DIR, "listings.csv")
EVENTS_FILE = os.path.join(DATA_DIR, "events.csv")
SUMMARY_FILE = os.path.join(DATA_DIR, "market_summary.csv")

LISTING_FIELDS = [
    "source_url", "post_time", "title", "status", "sold_detected_at", "days_to_sell",
    "model", "storage", "全新未拆封機", "battery_health", "price", "first_price",
    "warranty", "notes", "model_raw", "first_seen", "last_checked", "body_hash",
]
EVENT_FIELDS = ["time", "source_url", "event", "detail"]

STATUS_ACTIVE = "在售"
STATUS_PENDING = "交易中"
STATUS_SOLD = "已售出"
STATUS_DELETED = "已刪除"
OPEN_STATUSES = {STATUS_ACTIVE, STATUS_PENDING}

SYSTEM_PROMPT = """
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


# ==========================================
# 工具函式
# ==========================================
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def url_timestamp(url):
    """PTT 文章網址 M.<unix>.A.xxx.html 內含發文時間。"""
    m = re.search(r"/M\.(\d+)\.A\.", url)
    return int(m.group(1)) if m else None


def post_time_from_url(url):
    ts = url_timestamp(url)
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""


def fetch(url, max_retries=3):
    """回傳 (status_code, text)。404 直接回傳，不重試；連線失敗回傳 (None, None)。"""
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code in (200, 404):
                return r.status_code, r.text
            print(f"[WARN] 伺服器回傳異常狀態碼：{r.status_code}")
        except requests.exceptions.ConnectionError:
            wait = 15 * (attempt + 1)
            print(f"[WARN] 連線被重置，等待 {wait} 秒後第 {attempt + 1} 次重試...")
            time.sleep(wait)
        except Exception as e:
            print(f"[ERROR] 未知的網路錯誤：{e}")
            break
    return None, None


def polite_sleep(lo=1.0, hi=2.5):
    time.sleep(random.uniform(lo, hi))


def to_int(value):
    if value is None:
        return None
    m = re.search(r"\d[\d,]*", str(value))
    if not m:
        return None
    try:
        return int(m.group().replace(",", ""))
    except ValueError:
        return None


# ==========================================
# 型號 / 容量正規化
# ==========================================
_ROMAN = {"x": "X", "xr": "XR", "xs": "XS"}


def normalize_model(raw):
    """把 'iphone 11 pro'、'IPHONE15PM'、'i14 pro max' 等統一成 'iPhone 11 Pro' 格式。"""
    if not raw:
        return ""
    s = str(raw).lower().replace("iphone", " ").replace("愛鳳", " ")
    s = re.sub(r"[^\da-z\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^i\s*(?=\d)", "", s)  # i15 → 15

    # 縮寫：15pm / 15 pm → 15 pro max，15p → 15 pro
    s = re.sub(r"(\d+)\s*pm\b", r"\1 pro max", s)
    s = re.sub(r"(\d+)\s*p\b", r"\1 pro", s)
    s = re.sub(r"\bpromax\b", "pro max", s)
    s = re.sub(r"(\d+)(pro|plus|mini|max|e)\b", r"\1 \2", s)

    base = None
    m = re.search(r"\b(\d{1,2})(e)?\b", s)
    if m and 4 <= int(m.group(1)) <= 30:
        base = m.group(1) + ("e" if m.group(2) or re.search(rf"\b{m.group(1)}\s+e\b", s) else "")
    elif re.search(r"\bair\b", s):
        base = "Air"
    elif re.search(r"\bse\b", s):
        gen = re.search(r"\bse\s*(\d)\b", s)
        base = f"SE{gen.group(1)}" if gen else "SE"
    else:
        for k in ("xs", "xr", "x"):
            if re.search(rf"\b{k}\b", s):
                base = _ROMAN[k]
                break
    if base is None:
        return str(raw).strip()

    suffix = ""
    if "pro max" in s or re.search(r"\bpro\b.*\bmax\b", s):
        suffix = " Pro Max"
    elif re.search(r"\bpro\b", s):
        suffix = " Pro"
    elif re.search(r"\bplus\b", s):
        suffix = " Plus"
    elif re.search(r"\bmini\b", s):
        suffix = " mini"
    elif base in ("XS",) and re.search(r"\bmax\b", s):
        suffix = " Max"
    return f"iPhone {base}{suffix}"


def normalize_storage(raw):
    s = str(raw or "").strip().lower()
    m = re.search(r"\d+", s)
    if not m:
        return "未知"
    n = int(m.group())
    if "t" in s or n in (1, 2):
        return f"{n}TB"
    return f"{n}GB"


# ==========================================
# 文章解析與售出判斷
# ==========================================
SOLD_TITLE_KW = ["已售出", "已售", "售出", "已賣出", "已賣", "賣出", "sold", "已出售", "已結案", "結案"]
PENDING_KW = ["交易中", "已保留", "保留中", "已預訂", "已預定", "洽談中"]
# 版規模板裡會出現「售出」的句子，判斷前先剔除
RULE_NOISE = ["售出後修改價格至不可視者水桶並劣退"]
_SOLD_KW_RE = r"(已售出|已售|售出|已賣出|已賣|賣出|sold|已出售)"
# 行首是售出字樣（排除「售出後…」這類規則句），或整行以售出字樣結尾（如「iPhone 15 已售出 謝謝」）
_SOLD_LINE_RE = re.compile(r"^[\s\[\(【（]*" + _SOLD_KW_RE + r"(?![後前時])", re.I)
_SOLD_TAIL_RE = re.compile(_SOLD_KW_RE + r"[\s\W]*(謝謝.*|感謝.*)?$", re.I)


def parse_article(html):
    """回傳 dict(title, body)。body 為本文（不含推文、發信站資訊），用來算 hash 與送 LLM。"""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find(id="main-content")
    if main is None:
        return None
    title = ""
    for line in main.find_all("div", class_="article-metaline"):
        tag = line.find("span", class_="article-meta-tag")
        val = line.find("span", class_="article-meta-value")
        if tag and val and tag.text.strip() == "標題":
            title = val.text.strip()
    for cls in ("article-metaline", "article-metaline-right", "push"):
        for tag in main.find_all("div", class_=cls):
            tag.decompose()
    text = main.get_text()
    body = re.split(r"\n--\n※ 發信站|※ 發信站", text)[0].strip()
    return {"title": title, "body": body}


def body_hash(body):
    return hashlib.md5(body.encode("utf-8")).hexdigest()


def detect_status(title, body):
    """只看標題與本文判斷：已售出 / 交易中 / 在售。"""
    t = (title or "").lower()
    if any(kw in t for kw in SOLD_TITLE_KW):
        return STATUS_SOLD
    clean = body or ""
    for noise in RULE_NOISE:
        clean = clean.replace(noise, "")
    for line in clean.splitlines():
        line = line.strip()
        if not line:
            continue
        # 賣家通常在本文開頭或單獨一行寫「已售出」；長句中提到「售出」多半是規則說明，不採計
        if _SOLD_LINE_RE.match(line) or (len(line) <= 20 and _SOLD_TAIL_RE.search(line)):
            return STATUS_SOLD
    if any(kw in t for kw in PENDING_KW):
        return STATUS_PENDING
    return STATUS_ACTIVE


def is_iphone_sale_title(title):
    if not title or title.startswith("Re:") or title.startswith("Fw:"):
        return False
    if "[販售]" not in title:
        return False
    return bool(re.search(r"i\s*phone|愛鳳", title, re.I))


# ==========================================
# LLM 萃取
# ==========================================
def llm_extract(title, body):
    import ollama  # 延遲載入：--no-llm 模式不需要安裝 / 啟動 Ollama
    resp = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"標題：{title}\n\n{body}"},
        ],
        format="json",
    )
    return json.loads(resp["message"]["content"])


def build_fields(parsed):
    """把 LLM 回傳轉成 listing 欄位；非 iPhone 或無單機價格回傳 None。"""
    model_raw = parsed.get("model")
    if not model_raw or str(model_raw).lower() == "null":
        return None
    price = to_int(parsed.get("price"))
    if not price or price < 1000:  # 排除沒標價、或把「剩 5 個月保固」之類數字誤當價格
        return None
    brand_new = parsed.get("is_brand_new") is True
    warranty = str(parsed.get("warranty") or "")
    notes = str(parsed.get("notes") or "")
    if brand_new:
        battery, warranty = 100, "1年"
    else:
        battery = to_int(parsed.get("battery_health"))
        if battery is not None and not (50 <= battery <= 100):
            battery = None
        if any(kw in notes + warranty for kw in ["已過保", "無保固", "過保"]):
            warranty = "無保固"
        elif not warranty or warranty.lower() == "null":
            warranty = "未知"
    return {
        "model_raw": str(model_raw),
        "model": normalize_model(model_raw),
        "storage": normalize_storage(parsed.get("storage")),
        "全新未拆封機": "是" if brand_new else "否",
        "battery_health": battery if battery is not None else "",
        "price": price,
        "warranty": warranty,
        "notes": notes,
    }


# ==========================================
# 資料存取
# ==========================================
def load_listings(path=None):
    path = path or LISTINGS_FILE
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {row["source_url"]: row for row in csv.DictReader(f)}


def save_listings(listings, path=None):
    path = path or LISTINGS_FILE
    rows = sorted(listings.values(), key=lambda r: r.get("post_time", ""), reverse=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LISTING_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def log_event(url, event, detail="", path=None):
    path = path or EVENTS_FILE
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"time": now_str(), "source_url": url, "event": event, "detail": detail})
    print(f"    [EVENT] {event} {detail}")


MAX_CHECK_GAP_DAYS = 3  # 兩次檢查間隔超過這麼久，售出天數誤差太大，不採計


def mark_status(row, status, prev_checked=""):
    """更新狀態；第一次偵測到已售出時記錄時間與銷售天數。"""
    old = row.get("status") or STATUS_ACTIVE
    if status == old:
        return
    row["status"] = status
    if status == STATUS_SOLD and not row.get("sold_detected_at"):
        row["sold_detected_at"] = now_str()
        row["days_to_sell"] = ""
        try:
            posted = datetime.strptime(row["post_time"], "%Y-%m-%d %H:%M:%S")
            last = datetime.strptime(prev_checked, "%Y-%m-%d %H:%M:%S")
            if (datetime.now() - last).days <= MAX_CHECK_GAP_DAYS:
                row["days_to_sell"] = round((datetime.now() - posted).total_seconds() / 86400, 1)
        except (KeyError, ValueError):
            pass
    log_event(row["source_url"], "狀態變更", f"{old} → {status}")


# ==========================================
# 第一階段：掃描看板
# ==========================================
def scan_board(days, max_pages):
    cutoff = (datetime.now() - timedelta(days=days)).timestamp()
    url, found = INDEX_URL, []
    for page in range(max_pages):
        print(f"\n---> [SCAN] 第 {page + 1} 頁 {url}")
        code, html = fetch(url)
        if code != 200:
            print("[ERROR] 看板頁面連線失敗，停止翻頁。")
            break
        soup = BeautifulSoup(html, "html.parser")
        page_ts = []
        for ent in soup.find_all("div", class_="r-ent"):
            a = ent.find("div", class_="title").find("a")
            if not a:
                continue  # 已被刪除的文章
            link = BASE_URL + a["href"]
            ts = url_timestamp(link)
            if ts:
                page_ts.append(ts)
            if is_iphone_sale_title(a.text.strip()) and (ts or 0) >= cutoff:
                found.append({"title": a.text.strip(), "link": link})
        # 置底公告比較舊，所以用整頁「最新」一篇判斷是否已翻過截止日
        if page_ts and max(page_ts) < cutoff:
            print(f"[INFO] 已翻到 {days} 天前，停止翻頁。")
            break
        prev = soup.select_one("div.btn-group-paging a:nth-of-type(2)")
        if not prev or not prev.get("href"):
            break
        url = BASE_URL + prev["href"]
        polite_sleep()
    # 同一篇可能因翻頁時新文章湧入而重複出現
    uniq = {item["link"]: item for item in found}
    return list(uniq.values())


# ==========================================
# 第二、三階段：處理單篇文章
# ==========================================
def process_article(url, listings, use_llm, stats):
    code, html = fetch(url)
    row = listings.get(url)
    if code == 404:
        if row and row.get("status") in OPEN_STATUSES:
            mark_status(row, STATUS_DELETED)
            row["last_checked"] = now_str()
            stats["deleted"] += 1
        return
    if code != 200:
        print("    [ERROR] 無法取得文章，下次再試。")
        return
    art = parse_article(html)
    if art is None:
        return
    h = body_hash(art["body"])
    status = detect_status(art["title"], art["body"])

    if row is None:
        if not use_llm:
            return  # 新文章要等有 LLM 時才解析
        print("    [NEW] 新文章，送 LLM 解析。")
        fields = safe_extract(art, stats)
        if fields is None:
            # 仍記錄 hash，避免每次重跑；status 標成「略過」不進行情統計
            listings[url] = {"source_url": url, "post_time": post_time_from_url(url), "title": art["title"],
                             "status": "略過", "first_seen": now_str(), "last_checked": now_str(), "body_hash": h}
            return
        row = {"source_url": url, "post_time": post_time_from_url(url), "first_seen": now_str(),
               "status": STATUS_ACTIVE, "first_price": fields["price"], **fields}
        listings[url] = row
        stats["new"] += 1
        log_event(url, "新刊登", f"{fields['model']} {fields['storage']} ${fields['price']}")
    elif row.get("status") == "略過":
        row["last_checked"] = now_str()
        return
    elif row.get("body_hash") and row["body_hash"] != h and use_llm:
        print("    [UPDATE] 本文被編輯，重新解析。")
        fields = safe_extract(art, stats)
        if fields:
            old_price = to_int(row.get("price"))
            if old_price and fields["price"] != old_price:
                log_event(url, "價格變動", f"{old_price} → {fields['price']}")
                stats["price_changes"] += 1
            row.update(fields)

    prev_checked = row.get("last_checked") or row.get("first_seen", "")
    row["title"] = art["title"]
    row["body_hash"] = h
    row["last_checked"] = now_str()
    before = row.get("status")
    mark_status(row, status, prev_checked)
    if status == STATUS_SOLD and before != STATUS_SOLD:
        stats["sold"] += 1


def safe_extract(art, stats):
    try:
        return build_fields(llm_extract(art["title"], art["body"]))
    except Exception as e:
        print(f"    [ERR] LLM 解析失敗：{e}")
        stats["errors"] += 1
        return None


# ==========================================
# 第四階段：行情彙整
# ==========================================
def median(xs):
    return int(statistics.median(xs)) if xs else ""


def build_summary(listings, path=None):
    path = path or SUMMARY_FILE
    groups = {}
    for r in listings.values():
        if r.get("status") not in (STATUS_ACTIVE, STATUS_PENDING, STATUS_SOLD, STATUS_DELETED):
            continue
        price = to_int(r.get("price"))
        if not price or not r.get("model"):
            continue
        key = (r["model"], r.get("storage", ""), r.get("全新未拆封機", "否"))
        groups.setdefault(key, []).append((r, price))

    rows = []
    for (model, storage, new), items in groups.items():
        prices = [p for _, p in items]
        sold = [(r, p) for r, p in items if r["status"] == STATUS_SOLD]
        days = [float(r["days_to_sell"]) for r, _ in sold if r.get("days_to_sell") not in ("", None)]
        batt = [to_int(r.get("battery_health")) for r, _ in items if to_int(r.get("battery_health"))]
        rows.append({
            "model": model, "storage": storage, "全新未拆封機": new,
            "刊登數": len(items),
            "已售出數": len(sold),
            "售出率": f"{len(sold) / len(items):.0%}",
            "刊登價中位數": median(prices),
            "成交價中位數(已售標價)": median([p for _, p in sold]),
            "最低價": min(prices), "最高價": max(prices),
            "平均電池": round(sum(batt) / len(batt)) if batt else "",
            "售出天數中位數": round(statistics.median(days), 1) if days else "",
        })
    rows.sort(key=lambda r: (r["model"], r["storage"], r["全新未拆封機"]))
    fields = list(rows[0].keys()) if rows else ["model"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return rows


# ==========================================
# v1 資料匯入
# ==========================================
def migrate(v1_csv, listings):
    with open(v1_csv, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            url = r["source_url"]
            row = listings.get(url, {})
            row.update({
                "source_url": url,
                "post_time": post_time_from_url(url),
                "model_raw": r.get("model", ""),
                "model": normalize_model(r.get("model")),
                "storage": normalize_storage(r.get("storage")),
                "全新未拆封機": r.get("全新未拆封機", "否"),
                "battery_health": r.get("battery_health", ""),
                "price": to_int(r.get("price")) or "",
                "warranty": r.get("warranty", ""),
                "notes": r.get("notes", ""),
                "first_seen": row.get("first_seen") or r.get("scrape_timestamp", ""),
                "last_checked": r.get("scrape_timestamp", ""),
                "status": row.get("status") or (STATUS_SOLD if r.get("是否已售出") == "是" else STATUS_ACTIVE),
                "body_hash": row.get("body_hash", ""),  # 空的：下次回訪時補上，不會觸發 LLM
            })
            row.setdefault("first_price", row["price"])
            listings[url] = row  # 同一篇多列時，後面（較新）的覆蓋前面
    print(f"[MIGRATE] 匯入完成，共 {len(listings)} 篇。")


# ==========================================
# 主程式
# ==========================================
def main():
    ap = argparse.ArgumentParser(description="PTT MacShop iPhone 成交追蹤")
    ap.add_argument("--days", type=int, default=3, help="掃描看板時往回看幾天的新文章（預設 3）")
    ap.add_argument("--max-pages", type=int, default=30, help="掃描看板最多翻幾頁（預設 30）")
    ap.add_argument("--track-days", type=int, default=45, help="在售文章發文後持續回訪幾天（預設 45）")
    ap.add_argument("--no-llm", action="store_true", help="不呼叫 Ollama，只回訪既有文章更新狀態")
    ap.add_argument("--report-only", action="store_true", help="只重算行情彙整")
    ap.add_argument("--migrate", metavar="V1_CSV", help="匯入 v1 的 macshop_raw_data.csv")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    listings = load_listings()
    if args.migrate:
        migrate(args.migrate, listings)
        save_listings(listings)

    if not args.report_only and not args.migrate:
        stats = {"new": 0, "sold": 0, "deleted": 0, "price_changes": 0, "errors": 0}
        use_llm = not args.no_llm

        print("=" * 60 + "\n[INFO] 第一階段：掃描看板\n" + "=" * 60)
        targets = [] if not use_llm else scan_board(args.days, args.max_pages)
        print(f"[INFO] 看板上找到 {len(targets)} 篇 iPhone 販售文。")

        track_cutoff = (datetime.now() - timedelta(days=args.track_days)).timestamp()
        revisit = [u for u, r in listings.items()
                   if r.get("status") in OPEN_STATUSES and (url_timestamp(u) or 0) >= track_cutoff]
        queue = list(dict.fromkeys([t["link"] for t in targets] + revisit))
        print(f"[INFO] 另有 {len(revisit)} 篇在售文章需回訪，合計處理 {len(queue)} 篇。")

        print("=" * 60 + "\n[INFO] 第二、三階段：解析新文章 + 回訪追蹤\n" + "=" * 60)
        for i, url in enumerate(queue, 1):
            print(f"\n[{i}/{len(queue)}] {url}")
            try:
                process_article(url, listings, use_llm, stats)
            except Exception as e:
                print(f"    [ERR] {e}")
                stats["errors"] += 1
            if i % 10 == 0:
                save_listings(listings)  # 中途存檔，被中斷也不會白跑
            polite_sleep()
        save_listings(listings)
        print("\n" + "=" * 60)
        print(f"[DONE] 新刊登 {stats['new']}｜新售出 {stats['sold']}｜刪文 {stats['deleted']}"
              f"｜價格變動 {stats['price_changes']}｜錯誤 {stats['errors']}")

    rows = build_summary(listings)
    print(f"[REPORT] 行情彙整 {len(rows)} 組 → {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
