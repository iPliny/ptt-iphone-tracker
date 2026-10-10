"""
PTT MacShop iPhone 二手機成交追蹤 v2

v1 的問題：每次只看最新 2 頁，文章一旦被擠出前 2 頁就再也不會被回訪，
而賣家通常是「幾天後」才把標題改成已售出，所以成交狀態永遠抓不到。

v2 的流程（每次執行都做完這四步）：
  1. 掃描：往回翻頁，直到文章時間早於 --days 天前（上限 --max-pages 頁）。
  2. 萃取：新文章、或「本文」有被編輯（推文不算）的文章才解析欄位；
     預設依發文範本用規則萃取（雲端可跑）；有 ANTHROPIC_API_KEY 時，規則抓不到的文章改請 Claude 萃取；
     --extractor ollama 改用本機 LLM。
  3. 回訪：所有仍在售、且發文在 --track-days 天內的文章逐篇重新打開，
     只用標題/本文關鍵字判斷是否已售出或被刪除。
  4. 彙整：輸出 data/ 底下的 listings.csv（每篇文章一列、最新狀態）、events.csv（變動紀錄）、
     market_summary.csv（各型號行情）。

用法：
  python tracker.py                 # 完整執行（GitHub Actions 每 6 小時跑這個）
  python tracker.py --extractor ollama   # 改用本機 Ollama 萃取
  python tracker.py --track-only    # 只回訪既有文章、更新成交狀態
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
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

try:
    # 模擬瀏覽器 TLS 指紋；GitHub Actions 等雲端 IP 用一般 requests 會被 Cloudflare 擋（403）
    from curl_cffi import requests as cffi_requests
except ImportError:
    cffi_requests = None

# 所有不帶時區的時間欄位一律是台灣時間；GitHub Actions 主機預設是 UTC，
# 不設的話 now_str()、發文時間都會比 PTT 的編輯時間慢 8 小時。
os.environ["TZ"] = "Asia/Taipei"
time.tzset()

BASE_URL = "https://www.ptt.cc"
INDEX_URL = BASE_URL + "/bbs/MacShop/index.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
IMPERSONATE = ["chrome", "safari", "firefox"]  # 被 403 時依序換一種瀏覽器指紋
OLLAMA_MODEL = "qwen2.5:32b"
CLAUDE_MODEL = "claude-haiku-5-5"

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
LISTINGS_FILE = os.path.join(DATA_DIR, "listings.csv")
EVENTS_FILE = os.path.join(DATA_DIR, "events.csv")
SUMMARY_FILE = os.path.join(DATA_DIR, "market_summary.csv")
MULTI_FILE = os.path.join(DATA_DIR, "multi_items.csv")  # 一篇賣多樣商品時拆出的各支 iPhone（只算刊登價）
MULTI_FIELDS = ["source_url", "item_no", "post_time", "title", "model", "storage", "全新未拆封機",
                "battery_health", "price", "first_seen"]

LISTING_FIELDS = [
    "source_url", "post_time", "title", "status", "sold_detected_at", "days_to_sell",
    "model", "storage", "全新未拆封機", "battery_health", "price", "first_price",
    "warranty", "notes", "model_raw", "first_seen", "last_checked", "body_hash",
    "days_to_sell_basis",  # 觀測＝兩次檢查之間偵測到售出；推估＝用最後編輯時間推算；無法推估
    "private_msg_count",
    "last_edit_at", "price_checked_at",  # ISO 8601，台灣時間；不回填舊事件
    "color",  # 空白＝無法確定機身顏色
    "extractor",  # rules／claude／ollama：這列欄位由誰萃取；空白＝加入此欄前的舊資料
]
BASIS_OBSERVED = "觀測"
BASIS_ESTIMATED = "推估"
BASIS_UNKNOWN = "無法推估"
EVENT_FIELDS = ["time", "source_url", "event", "detail"]
PRICE_EVENT_FIELDS = ["time", "source_url", "detail", "occurred_at", "detected_at", "time_basis"]
TAIPEI = timezone(timedelta(hours=8))

STATUS_ACTIVE = "在售"
STATUS_PENDING = "交易中"
STATUS_SOLD = "已售出"
STATUS_DELETED = "已刪除"
OPEN_STATUSES = {STATUS_ACTIVE, STATUS_PENDING}
MULTI_STATUS = "多品項"  # multi_items.csv 的品項，只在彙整時使用

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


def taipei_now():
    return datetime.now(TAIPEI).replace(microsecond=0)


def parse_aware_time(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(TAIPEI) if dt.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def url_timestamp(url):
    """PTT 文章網址 M.<unix>.A.xxx.html 內含發文時間。"""
    m = re.search(r"/M\.(\d+)\.A\.", url)
    return int(m.group(1)) if m else None


def post_time_from_url(url):
    ts = url_timestamp(url)
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""


def _get(url, attempt):
    if cffi_requests is not None:
        return cffi_requests.get(url, impersonate=IMPERSONATE[attempt % len(IMPERSONATE)], timeout=20)
    return requests.get(url, headers=HEADERS, timeout=20)


def fetch(url, max_retries=3):
    """回傳 (status_code, text)。404 直接回傳，不重試；連線失敗回傳 (None, None)。"""
    for attempt in range(max_retries):
        try:
            r = _get(url, attempt)
            if r.status_code in (200, 404):
                return r.status_code, r.text
            print(f"[WARN] 伺服器回傳異常狀態碼：{r.status_code}")
            time.sleep(5 * (attempt + 1))
        except Exception as e:
            wait = 15 * (attempt + 1)
            print(f"[WARN] 連線失敗（{type(e).__name__}），等待 {wait} 秒後第 {attempt + 1} 次重試...")
            time.sleep(wait)
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
    s = s.replace("promax", " pro max")
    s = re.sub(r"(\d)(?=[a-z])|(pro|max|plus)(?=\d)", r"\1\2 ", s)  # 18pro → 18 pro、pro256g → pro 256 g
    s = re.sub(r"\s+", " ", s).strip()

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
    elif re.search(r"\bse\s*\d?\b", s):
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


PM_KEYWORD_RE = re.compile(r"私|站內|密你|已密")
PM_NOISE = ("私密", "私人", "隱私", "自私", "私下", "私心", "公私", "勿私", "不私", "別私", "不要私")


def count_private_msgs(pushes, author):
    """推文以 (ID, 內容) 傳入；排除原 PO 與誤判詞，同一人只計一次。"""
    buyers = set()
    for userid, content in pushes:
        if not userid or userid == author:
            continue
        for noise in PM_NOISE:
            content = content.replace(noise, "")
        if PM_KEYWORD_RE.search(content):
            buyers.add(userid)
    return len(buyers)


def parse_article(html):
    """回傳標題、本文、最後編輯時間與私訊人數；本文不含推文，供 hash 與 LLM 使用。"""
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find(id="main-content")
    if main is None:
        return None
    title = ""
    author = ""
    for line in main.find_all("div", class_="article-metaline"):
        tag = line.find("span", class_="article-meta-tag")
        val = line.find("span", class_="article-meta-value")
        if tag and val and tag.text.strip() == "標題":
            title = val.text.strip()
        if tag and val and tag.text.strip() == "作者":
            parts = val.text.split()
            author = parts[0] if parts else ""
    pushes = []
    for push in main.find_all("div", class_="push"):
        userid = push.find("span", class_="push-userid")
        content = push.find("span", class_="push-content")
        if userid and content:
            pushes.append((userid.text.strip(), re.sub(r"^:\s*", "", content.text.strip())))
    pm_count = count_private_msgs(pushes, author)
    for cls in ("article-metaline", "article-metaline-right", "push"):
        for tag in main.find_all("div", class_=cls):
            tag.decompose()
    text = main.get_text()
    body = re.split(r"\n--\n※ 發信站|※ 發信站", text)[0].strip()
    return {"title": title, "body": body, "last_edit": last_edit_time(text), "pm_count": pm_count}


_EDIT_RE = re.compile(r"※ 編輯: \S+ \([^)]*\), (\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})")


def last_edit_time(text):
    """文末「※ 編輯: id (ip 地區), 09/27/2026 19:17:06」的最後一筆，回傳 datetime 或 None。"""
    stamps = _EDIT_RE.findall(text)
    if not stamps:
        return None
    try:
        return datetime.strptime(stamps[-1], "%m/%d/%Y %H:%M:%S")
    except ValueError:
        return None  # 最後一筆格式錯誤時，不誤用更早的編輯紀錄


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
# 規則萃取（預設，不需 LLM；依 MacShop 發文範本）
# 範本欄位：[型號] [規格] [保固] [盒裝配件] [售價] [交易方式/地點] [連絡方式] [商品照/補充說明]
# ==========================================
_FIELD_RE = re.compile(r"^\s*[\[【［]\s*([^\]】］\n]{1,12}?)\s*[\]】］]\s*[:：]?\s*(.*)$")
_ACCESSORY_RE = re.compile(r"殼|保護貼|玻璃貼|鏡頭貼|充電器|充電線|傳輸線|豆腐頭|耳機|錶帶|卡夾|支架|包膜")
_BRAND_NEW_RE = re.compile(r"全新未拆|未拆封|未開通|未啟用|全新未使用|膜未撕")
# 「配件全新未使用」「傳輸線全新」這類描述的是配件，不是機身
_ACCESSORY_NEW_RE = re.compile(r"(配件|傳輸線|充電線|線材|耳機|殼|保護貼|玻璃貼|保貼|卡針|豆腐頭)[^，,。\n]{0,15}?(全新|未使用|未拆)[^，,。\n]*")
_NUMBERED_LINE_RE = re.compile(r"^\s*[1-9]\s*[.、)）:：]?\s*\S", re.M)
VALID_STORAGE_GB = {32, 64, 128, 256, 512}
_BATTERY_RE = re.compile(r"(?:電池|健康度|battery|bh)[^\d\n]{0,10}(\d{2,3})\s*%?", re.I)
_DATE_RE = re.compile(r"(20\d{2})\s*[/.\-年]\s*(\d{1,2})(?:\s*[/.\-月]\s*(\d{1,2}))?")


def split_template(body):
    """把本文依 [欄位] 切開；值可能在同一行或下一行。回傳 {欄位名: 內容}。"""
    fields, key = {}, None
    for line in body.splitlines():
        m = _FIELD_RE.match(line)
        if m:
            key = m.group(1).strip()
            fields[key] = m.group(2).strip()
        elif key is not None:
            fields[key] = (fields[key] + "\n" + line.strip()).strip()
    return fields


def split_blocks(body):
    """
    一篇賣多樣商品時，賣家常把整份範本重複貼好幾次（iPhone 一段、Apple Watch 一段）。
    型號欄再次出現就視為新的一段；回傳 [{欄位名: 內容}, ...]。
    """
    blocks, fields, key = [], {}, None
    for line in body.splitlines():
        m = _FIELD_RE.match(line)
        if m:
            key = m.group(1).strip()
            if key in fields and re.search(r"型號|品名|物品", key):
                blocks.append(fields)
                fields = {}
            # 其他欄位重複（兩個 [規格]、兩個 [補充說明]）只是賣家多貼一次，接在原欄位後面
            fields[key] = (fields[key] + "\n" + m.group(2).strip()).strip() if key in fields else m.group(2).strip()
        elif key is not None:
            fields[key] = (fields[key] + "\n" + line.strip()).strip()
    if fields or not blocks:
        blocks.append(fields)
    return blocks


def _looks_like_iphone(fields):
    text = _field(fields, "型號", "品名", "物品") + "\n" + _field(fields, "規格", "容量", "顏色")
    return bool(re.search(r"i\s*phone|愛鳳", text, re.I) or re.match(r"\s*i?\s*1\d", text, re.I))


def _field(fields, *names):
    for k, v in fields.items():
        if any(n in k for n in names):
            return v
    return ""


def parse_price(text):
    """'41,500元'、'NT$ 20000'、'2.5萬' → int；取第一個合理的金額。"""
    text = text.replace(",", "").replace("，", "")
    # 先拿掉日期，例如「Apple care+ 到 2028/1/22」的 2028 不是價格
    text = re.sub(r"(?<!\d)(?:19|20)\d{2}\s*(?:年|[/／\-.]\s*\d{1,2}(?!\d))(?:\s*[/／\-.月]\s*\d{1,2}\s*日?)?", " ", text)
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(萬|w|k|千)?", text, re.I):
        n, unit = float(m.group(1)), (m.group(2) or "").lower()
        n *= {"萬": 10000, "w": 10000, "k": 1000, "千": 1000}.get(unit, 1)
        if 1000 <= n <= 200000:
            return int(n)
    return None


def parse_storage(*texts):
    """依序在各段文字找容量，跳過不合理的數字（如筆誤 265G）。"""
    for t in texts:
        for m in re.finditer(r"(\d{1,4})\s*(g|gb|t|tb)\b|(?<!\d)(\d{2,3})(?!\d)", t or "", re.I):
            if m.group(2):
                n, unit = int(m.group(1)), m.group(2).lower()
                if unit.startswith("t") and n in (1, 2):
                    return f"{n}TB"
                if unit.startswith("g") and n in VALID_STORAGE_GB:
                    return f"{n}GB"
            elif int(m.group(3)) in (64, 128, 256, 512):
                return f"{m.group(3)}GB"
    return None


# Apple 台灣正式名稱，查證 2026-10-07：https://support.apple.com/zh-tw/108044
# 別名只是文章寫法，並非 Apple 官方別名。完整對照與來源見 docs/colors.md。
def _palette(**colors):
    return {name: aliases.split("|") for name, aliases in colors.items()}


_BASIC_COLORS = _palette(黑色="黑|Black", 白色="白|White", 藍色="藍|Blue", 綠色="綠|Green",
                         紫色="紫|Purple", 黃色="黃|Yellow", 粉紅色="粉|粉色|粉紅|Pink",
                         **{"(PRODUCT)RED": "紅|紅色|Red|PRODUCT RED|（PRODUCT）RED"})
_SILVER = "銀|白|白色|Silver|White"
_GOLD = "金|Gold"
_GRAY = "灰|灰色|黑|黑色|太空灰|Space Gray|Space Grey|Black"
_GRAPHITE = "石墨|灰|灰色|黑|黑色|Graphite|Black"
_TITANIUM = _palette(黑色鈦金屬="黑|黑色|黑鈦|黑鈦色|黑色鈦|Black|Black Titanium",
                     白色鈦金屬="白|白色|白鈦|白鈦色|白色鈦|銀|銀色|White|White Titanium|Silver",
                     原色鈦金屬="原鈦|原鈦色|原色鈦|原色鈦金|原鈦金|鈦色|自然鈦|原色|Natural|Natural Titanium")
COLOR_TABLE = {
    "iPhone 8": _palette(銀色=_SILVER, 金色=_GOLD, 太空灰色=_GRAY,
                         **{"(PRODUCT)RED": "紅|紅色|Red|PRODUCT RED|（PRODUCT）RED"}),
    "iPhone XS": _palette(銀色=_SILVER, 金色=_GOLD, 太空灰色=_GRAY),
    "iPhone 11": {k: v for k, v in _BASIC_COLORS.items() if k not in ("藍色", "粉紅色")},
    "iPhone 11 Pro": _palette(銀色=_SILVER, 金色=_GOLD, 太空灰色=_GRAY, 夜幕綠色="綠|綠色|夜幕綠|Midnight Green|Green"),
    "iPhone 12": {k: v for k, v in _BASIC_COLORS.items() if k not in ("黃色", "粉紅色")},
    "iPhone 12 Pro": _palette(銀色=_SILVER, 金色=_GOLD, 石墨色=_GRAPHITE, 太平洋藍色="藍|藍色|太平洋藍|Pacific Blue|Blue"),
    "iPhone 13": {**{k: v for k, v in _BASIC_COLORS.items() if k in ("藍色", "粉紅色", "綠色", "(PRODUCT)RED")},
                  **_palette(星光色="星光|白|白色|Starlight|White", 午夜色="午夜|黑|黑色|Midnight|Black")},
    "iPhone 13 Pro": _palette(銀色=_SILVER, 金色=_GOLD, 石墨色=_GRAPHITE,
                              天峰藍色="藍|藍色|天峰藍|Sierra Blue|Blue", 松嶺青色="綠|綠色|松嶺青|松嶺綠|Alpine Green|Green"),
    "iPhone 14": {**{k: v for k, v in _BASIC_COLORS.items() if k in ("藍色", "紫色", "黃色", "(PRODUCT)RED")},
                  **_palette(星光色="星光|白|白色|Starlight|White", 午夜色="午夜|黑|黑色|Midnight|Black")},
    "iPhone 14 Pro": _palette(銀色=_SILVER, 金色=_GOLD, 太空黑色="黑|黑色|太空黑|Space Black|Black", 深紫色="紫|紫色|深紫|Deep Purple|Purple"),
    "iPhone 15": {k: v for k, v in _BASIC_COLORS.items() if k in ("黑色", "藍色", "綠色", "黃色", "粉紅色")},
    "iPhone 15 Pro": {**_TITANIUM, **_palette(藍色鈦金屬="藍|藍色|藍鈦|藍鈦色|藍色鈦|Blue|Blue Titanium")},
    "iPhone 16": {**{k: v for k, v in _BASIC_COLORS.items() if k in ("黑色", "白色", "粉紅色")},
                  **_palette(湖水綠色="綠|綠色|湖水綠|Teal|Green", 湛海藍色="藍|藍色|湛海藍|Ultramarine|Blue")},
    "iPhone 16 Pro": {**_TITANIUM, **_palette(沙漠色鈦金屬="沙漠金|沙漠鈦|沙漠鈦色|沙漠色|沙漠|金|金色|Desert|Desert Titanium|Gold")},
    "iPhone 16e": {k: v for k, v in _BASIC_COLORS.items() if k in ("黑色", "白色")},
    "iPhone 17": {**{k: v for k, v in _BASIC_COLORS.items() if k in ("黑色", "白色")},
                  **_palette(霧藍色="霧藍|藍|藍色|Mist Blue|Blue", 鼠尾草綠色="鼠尾草綠|綠|綠色|Sage|Green", 薰衣草紫色="薰衣草|薰衣草紫|紫|紫色|Lavender|Purple")},
    "iPhone 17 Pro": _palette(銀色=_SILVER, 宇宙橙色="宇宙橙|宇宙橘色|宇宙橘|橙|橙色|橘|橘色|Cosmic Orange|Orange",
                              藏藍色="藏藍|深藍色|深藍|藍|藍色|Deep Blue|Blue"),
    "iPhone Air": _palette(太空黑色="太空黑|黑|黑色|Space Black|Black", 雲白色="雲白|白|白色|Cloud White|White",
                           天藍色="天藍|藍|藍色|Sky Blue|Blue", 淺金色="淺金|金|金色|Light Gold|Gold"),
    "iPhone 17e": {**{k: v for k, v in _BASIC_COLORS.items() if k in ("黑色", "白色")},
                   **_palette(嫩粉色="嫩粉|粉|粉色|粉紅|粉紅色|Soft Pink|Pink")},
    # 已經 Apple 台灣官網核實：https://www.apple.com/tw/iphone-18-pro/specs/
    "iPhone 18 Pro": _palette(黑色="黑|Black", 銀色=_SILVER, 冰川藍色="冰川藍|藍|藍色|Glacier Blue|Blue",
                              勃根地紅色="勃根地紅|紅|紅色|Burgundy|Burgundy Red|Red"),
}
# Plus / mini / Pro Max 與對應系列共用色盤；不替不存在的型號推測色盤。
for _base, _suffixes in {
    "iPhone 8": (" Plus",), "iPhone XS": (" Max",),
    "iPhone 11 Pro": (" Max",), "iPhone 12": (" mini",), "iPhone 12 Pro": (" Max",),
    "iPhone 13": (" mini",), "iPhone 13 Pro": (" Max",), "iPhone 14": (" Plus",),
    "iPhone 14 Pro": (" Max",), "iPhone 15": (" Plus",), "iPhone 15 Pro": (" Max",),
    "iPhone 16": (" Plus",), "iPhone 16 Pro": (" Max",), "iPhone 17 Pro": (" Max",),
    "iPhone 18 Pro": (" Max",),
}.items():
    for _suffix in _suffixes:
        COLOR_TABLE[_base + _suffix] = COLOR_TABLE[_base]


def _color_aliases(palette):
    return {alias.casefold(): name for name, aliases in palette.items()
            for alias in [name, name.removesuffix("色"), *aliases]}


_COLOR_ALIASES = {m: _color_aliases(p) for m, p in COLOR_TABLE.items()}
# 全色盤最長字串優先：不把「沙漠色鈦金屬」內的「金」誤認成別種顏色。
_COLOR_TOKENS = sorted({a for p in _COLOR_ALIASES.values() for a in p}, key=lambda a: (-len(a), a))
_COLOR_RE = re.compile("|".join((r"(?<![a-z])" + re.escape(a) + r"(?![a-z])")
                             if a.isascii() else re.escape(a) for a in _COLOR_TOKENS), re.I)
_COLOR_ACCESSORY_RE = re.compile(r"(?:" + _COLOR_RE.pattern + r"|透明)(?:(?!" + _COLOR_RE.pattern + r")[^\n，,/+]){0,4}[殼套貼膜線頭盒]", re.I)


def _color_matches(text):
    """僅處理呼叫者提供的欄位；回傳原始詞供預覽稽核。"""
    text = re.sub(r"^\s*\[販售\]\s*", "", text or "")
    text = _COLOR_ACCESSORY_RE.sub(" ", text)
    text = re.sub(r"現金|訂金|定金|銀行|黑貓(?:宅配)?|紅包|白蘋果|小白點", " ", text)
    return text, list(_COLOR_RE.finditer(text))


def parse_color(model, *texts):
    """依欄位優先序找機身顏色；衝突、不符色盤、多機來源一律留空。"""
    aliases = _COLOR_ALIASES.get(model)
    if not aliases:
        return ""
    for source in texts:
        text, matches = _color_matches(source)
        # 標題含第二支 iPhone / Air 或多個容量，不把其中一支的顏色套到整篇。
        phones = re.findall(r"i\s*phone|(?<![a-z])air(?![a-z])", text, re.I)
        phones = len(phones) - len(re.findall(r"i\s*phone\s*air", text, re.I))
        capacities = re.findall(r"\d+\s*(?:gb|tb|g|t)(?![a-z])", text, re.I)
        if phones > 1 or len(capacities) > 1:
            return ""
        if matches:
            colors = {aliases.get(m.group().casefold()) for m in matches}
            return next(iter(colors)) if len(colors) == 1 and None not in colors else ""
    return ""


def backfill_colors(listings):
    """用既存標題補空白顏色，不抓文章、不寫事件。回傳補值筆數。"""
    n = 0
    for row in listings.values():
        if (not row.get("color") and row.get("model") and
                row.get("status") in (STATUS_ACTIVE, STATUS_PENDING, STATUS_SOLD, STATUS_DELETED)):
            color = parse_color(row["model"], row.get("title", ""))
            if color:
                row["color"] = color
                n += 1
    return n


def strip_signature(text):
    text = re.split(r"\n--+\s*\n|\n-{3,}", "\n" + text)[0]
    return "\n".join(l for l in text.splitlines() if not l.strip().lower().startswith("sent from"))


def is_brand_new(title, fields):
    """機身全新未拆才算；配件全新、已過保、電池非 100% 都不算。"""
    if re.search(r"過保|無保", _field(fields, "保固")):
        return False
    bh = _BATTERY_RE.search("\n".join(fields.values()))
    if bh and int(bh.group(1)) < 100:
        return False
    if re.search(r"全新|未拆", title) and "二手" not in title:
        return True
    text = "\n".join(v for k, v in fields.items() if not any(n in k for n in ("交易", "連絡", "聯絡")))
    return bool(_BRAND_NEW_RE.search(_ACCESSORY_NEW_RE.sub("", text)))


def parse_warranty(text):
    t = (text or "").strip()
    if not t:
        return None
    if re.search(r"過保|^無|無保|沒有保固|已過", t):
        return "無保固"
    m = _DATE_RE.search(t)
    if m:
        return "/".join(g for g in m.groups() if g)
    if re.search(r"一年|1年|開通", t):
        return "一年"
    return t.splitlines()[0][:30]


_CANONICAL_MODEL_RE = re.compile(
    r"iPhone (?:(?:\d{1,2}e?|SE\d?|Air)(?: Pro Max| Pro| Plus| mini)?|X|XR|XS(?: Max)?)")


def is_accessory_post(title, storage):
    """標題提到殼、保護貼等配件，又找不到容量 → 賣的是配件（標題的型號只是適用機型）。"""
    bare = re.sub(r"^\[[^\]]*\]\s*", "", title or "")
    return bool(_ACCESSORY_RE.search(bare)) and storage in ("", "未知", None)


def misparsed_reason(row):
    """舊規則留下、現在看得出是誤判的列：回傳原因，正常則回傳 None。"""
    model = row.get("model") or ""
    if model and not _CANONICAL_MODEL_RE.fullmatch(model):
        return f"不存在的型號 {model}"
    if is_accessory_post(row.get("title"), row.get("storage")):
        return "配件"
    return None


def not_single_iphone(art):
    """新規則明確判定不是單支 iPhone：配件文，或一篇賣多支。只是抓不到售價之類的不算。"""
    raw = rule_extract(art["title"], art["body"])
    return is_accessory_post(art["title"], raw["storage"]) or bool(extract_items(art["title"], art["body"]))


def skipped_from(url, path=None):
    """events.csv 裡這篇最後一次「排除誤判」之前的狀態；沒有就回傳 None。"""
    path = path or EVENTS_FILE
    prev = None
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for e in csv.DictReader(f):
                if e.get("source_url") == url and e.get("event") == "排除誤判":
                    m = re.match(r"(\S+) → 略過", e.get("detail", ""))
                    prev = m.group(1) if m else None
    return prev


def drop_misparsed(listings):
    """把誤判成 iPhone 的列改成「略過」，網站、週報、行情都不再計入。回傳處理筆數。"""
    n = 0
    for url, row in listings.items():
        if row.get("status") not in (STATUS_ACTIVE, STATUS_PENDING, STATUS_SOLD, STATUS_DELETED):
            continue
        reason = misparsed_reason(row)
        if reason:
            log_event(url, "排除誤判", f"{row.get('status')} → 略過（{reason}）")
            row["status"] = "略過"
            n += 1
    return n


def _pick_model(sources, context=""):
    """依序看各段文字，回傳第一個能確定的單一型號；都不行回傳 None。"""
    for source in sources:
        if not source or not re.search(r"i\s*phone|愛鳳", context + source, re.I):
            continue
        # 「保固至2026/10/4」的 10 不是代數
        undated = _DATE_RE.sub(" ", source)
        numbers = set(re.findall(r"(?<![\d.])(1[0-9]|[4-9])(?:\s*(?:pro|plus|mini|max|e)\b|\b)", undated, re.I))
        cand = normalize_model(source)
        # 沒寫代數（iPhone Pro Max）或不存在的組合（iPhone X Pro）→ 改看下一個來源
        if _CANONICAL_MODEL_RE.fullmatch(cand) and len(numbers) <= 1 and not _ACCESSORY_RE.search(source):
            return cand
    return None


def rule_extract(title, body):
    """回傳與 LLM 相同格式的 dict；無法確定是單一 iPhone 時 model 為 None。"""
    body = strip_signature(body)
    blocks = split_blocks(body)
    iphone_blocks = [b for b in blocks if _looks_like_iphone(b)]
    # 有 iPhone 那段就只用那段的欄位，避免被後面其他商品的售價、電池覆蓋
    fields = iphone_blocks[0] if iphone_blocks else blocks[0]
    model_text = _field(fields, "型號", "品名", "物品")
    spec = _field(fields, "規格", "容量", "顏色")
    price_text = _field(fields, "售價", "價格", "價錢")
    note = _field(fields, "補充", "說明", "備註", "附註")
    bare_title = re.sub(r"^\[[^\]]*\]\s*", "", title)

    # 一篇賣多支（型號欄是 1. 2. 編號清單）→ 價格無法對應單機，略過
    multi = len(_NUMBERED_LINE_RE.findall(model_text)) >= 2
    # 型號欄常只寫 A2633、MG6K4ZP/A 這類料號，依序改用規格欄、標題
    # 型號欄只看第一行：下一行常是「可憑商品序號至 Apple官網查詢」之類的附註
    model_line = next((l for l in model_text.splitlines() if l.strip()), "")
    model = _pick_model((model_line, spec, bare_title), title)
    if model:
        # 型號欄只寫「iPhone18」、標題寫「18 Pro」：同一代時以標題較完整的型號為準
        refined = normalize_model(bare_title)
        if _CANONICAL_MODEL_RE.fullmatch(refined) and refined.startswith(model + " "):
            model = refined
    storage = parse_storage(spec, model_text, bare_title)
    if multi or len(iphone_blocks) > 1 or is_accessory_post(title, storage):
        # 分段賣兩支以上 iPhone 或賣的是配件，同樣略過
        model = None

    battery = None
    m = _BATTERY_RE.search("\n".join(fields.values()) if len(blocks) > 1 else body)
    if m and 50 <= int(m.group(1)) <= 100:
        battery = int(m.group(1))

    # 去掉網址與賣家沒刪的發文範本提示
    note = "\n".join(l for l in note.splitlines() if not re.search(r"水桶|板規|請再次確認|詳閱|需附實物照|入鏡", l))
    notes = re.sub(r"https?://\S+", "", note)
    notes = re.sub(r"\s+", " ", notes).strip()[:120]
    return {
        "model": model,
        "storage": storage,
        "color": parse_color(model, _field(fields, "顏色"), _field(fields, "規格"), _field(fields, "容量"), model_line, bare_title),
        "price": parse_price(price_text) if price_text else None,
        "battery_health": battery,
        "warranty": parse_warranty(_field(fields, "保固")),
        "notes": notes,
        "is_brand_new": is_brand_new(title, fields),
    }


# ==========================================
# 一篇賣多樣商品：拆出各支 iPhone（只用來算刊登價）
# ==========================================
_ITEM_NO_RE = re.compile(r"^\s*([1-9])\s*(?:[.、)）:：]\s*|(?=[^\d\s.,]))(.*)$")


def _numbered(text):
    """'1.xxx\n2.yyy' → {1: 'xxx', 2: 'yyy'}；沒編號的行接在上一項後面。"""
    items, cur = {}, None
    for line in (text or "").splitlines():
        m = _ITEM_NO_RE.match(line)
        if m:
            cur = int(m.group(1))
            items[cur] = (items.get(cur, "") + "\n" + m.group(2)).strip()
        elif cur is not None and line.strip():
            items[cur] += "\n" + line.strip()
    return items


def _plain_lines(text):
    """沒編號的多行欄位：去掉網址、空行與「二手」這類太短的行。"""
    return [l.strip() for l in (text or "").splitlines()
            if len(l.strip()) > 3 and not re.search(r"https?://", l)]


def _split_field(text, n, numbered_keys):
    """把一個欄位拆成和品項對應的 n 段；拆不出來時每項共用整段。"""
    nums = _numbered(text)
    if set(nums) >= set(numbered_keys):
        return [nums[k] for k in numbered_keys]
    parts = [p for p in re.split(r"\s*[/／]\s*", (text or "").strip()) if p]
    if len(parts) == n and all(parse_price(p) for p in parts):
        return parts
    return [text or ""] * n


def _item(model_text, spec, price_text, warranty, extra=""):
    model = _pick_model((model_text, spec), "")
    # 只看第一行：下一行常是「兩個一起帶走 1600」這類合購價或發文範本的提示
    first = next((l for l in (price_text or "").splitlines() if l.strip()), "")
    price = parse_price(first) if first else None
    if not model or not price:
        return None
    fields = {"型號": model_text, "規格": spec, "保固": warranty, "說明": extra}
    m = _BATTERY_RE.search("\n".join(fields.values()))
    battery = int(m.group(1)) if m and 50 <= int(m.group(1)) <= 100 else None
    brand_new = is_brand_new(model_text + " " + spec, fields)
    return {"model": model, "storage": parse_storage(spec, model_text), "price": price,
            "battery_health": 100 if brand_new else battery, "is_brand_new": brand_new}


def extract_items(title, body):
    """一篇賣多樣商品（編號清單、或重複貼好幾段範本）時，回傳每支 iPhone 的型號／容量／售價。

    非 iPhone 的品項、找不到對應售價的品項略過；不是多品項的文章回傳 []。"""
    body = strip_signature(body)
    blocks = split_blocks(body)
    iphone_blocks = [b for b in blocks if _looks_like_iphone(b)]
    if len(iphone_blocks) > 1:  # 每支 iPhone 各貼一段範本
        items = (_item(_field(b, "型號", "品名", "物品"), _field(b, "規格", "容量", "顏色"),
                       _field(b, "售價", "價格", "價錢"), _field(b, "保固"), _field(b, "盒裝", "補充", "說明"))
                 for b in iphone_blocks)
        return [i for i in items if i]
    fields = iphone_blocks[0] if iphone_blocks else blocks[0]
    model_text = _field(fields, "型號", "品名", "物品")
    spec, price_text = _field(fields, "規格", "容量", "顏色"), _field(fields, "售價", "價格", "價錢")
    warranty, extra = _field(fields, "保固"), _field(fields, "盒裝", "補充", "說明")
    nums = _numbered(model_text)
    if len(nums) >= 2:
        keys = sorted(nums)
        names = [nums[k] for k in keys]
    else:
        # 沒編號、一行一個品項（例：iPhone 18 Pro Max A3717 / iPhone 16 Pro Max A3296），售價也一行一個
        names, prices = _plain_lines(model_text), [l for l in _plain_lines(price_text) if parse_price(l)]
        if len(names) < 2 or len(prices) != len(names):
            return []
        specs = _plain_lines(spec)
        specs = specs if len(specs) == len(names) else [spec] * len(names)
        return [i for i in (_item(n, s, p, warranty) for n, s, p in zip(names, specs, prices)) if i]
    n = len(keys)
    cols = [_split_field(t, n, keys) for t in (spec, price_text, warranty, extra)]
    if cols[1] == [price_text] * n and n > 1:
        return []  # 售價沒有逐項寫，無法對應
    return [i for i in (_item(name, *vals) for name, *vals in zip(names, *cols)) if i]


def load_multi(path=None):
    path = path or MULTI_FILE
    out = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                out.setdefault(row["source_url"], []).append(row)
    return out


def save_multi(multi, path=None):
    path = path or MULTI_FILE
    rows = sorted((r for items in multi.values() for r in items), key=lambda r: int(r["item_no"]))
    rows.sort(key=lambda r: (r.get("post_time", ""), r["source_url"]), reverse=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MULTI_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def record_multi(url, art, multi, first_seen=None):
    """把多品項文章拆出的 iPhone 記進 multi；沒有就移除舊紀錄。回傳筆數。"""
    multi.pop(url, None)
    if EXTRACTOR == "ollama":
        return 0
    items = extract_items(art["title"], art["body"])
    if items:
        multi[url] = [{"source_url": url, "item_no": n, "post_time": post_time_from_url(url), "title": art["title"],
                       "model": it["model"], "storage": it["storage"],
                       "全新未拆封機": "是" if it["is_brand_new"] else "否",
                       "battery_health": it["battery_health"] or "", "price": it["price"],
                       "first_seen": first_seen or now_str()} for n, it in enumerate(items, 1)]
    return len(items)


# ==========================================
# LLM 萃取（選用：本機有 Ollama 時可用 --extractor ollama）
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


_NULLABLE = lambda t: {"anyOf": [{"type": t}, {"type": "null"}]}
CLAUDE_SCHEMA = {
    "type": "object",
    "properties": {
        "model": _NULLABLE("string"),
        "storage": _NULLABLE("string"),
        "battery_health": _NULLABLE("integer"),
        "price": _NULLABLE("integer"),
        "warranty": _NULLABLE("string"),
        "notes": {"type": "string"},
        "is_brand_new": {"type": "boolean"},
    },
    "required": ["model", "storage", "battery_health", "price", "warranty", "notes", "is_brand_new"],
    "additionalProperties": False,
}
_claude_client = None


def claude_extract(title, body):
    """規則抓不到的文章交給 Claude；用 JSON schema 限定輸出格式，回傳與 rule_extract 相同鍵的 dict。"""
    global _claude_client
    if _claude_client is None:
        import anthropic  # 延遲載入：只用規則時不需要安裝
        _claude_client = anthropic.Anthropic()  # 讀 ANTHROPIC_API_KEY；程式裡不放金鑰
    resp = _claude_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"標題：{title}\n\n{body}"}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": CLAUDE_SCHEMA}},
    )
    if resp.stop_reason != "end_turn":
        raise RuntimeError(f"Claude 未完成萃取（{resp.stop_reason}）")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


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
        "color": parsed.get("color") or "",
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


def log_event(url, event, detail="", path=None, *, event_time=None):
    path = path or EVENTS_FILE
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=EVENT_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"time": event_time or now_str(), "source_url": url, "event": event, "detail": detail})
    print(f"    [EVENT] {event} {detail}")


def log_price_change(row, new_price, last_edit, detected_at):
    """價格確實變動才呼叫；保存本次頁面的編輯時間，不再隨後續編輯變動。"""
    url = row["source_url"]
    detail = f"{to_int(row.get('price'))} → {new_price}"
    edit = last_edit.replace(tzinfo=TAIPEI) if last_edit is not None else None
    previous = parse_aware_time(row.get("price_checked_at"))
    posted_ts = url_timestamp(url)
    posted = datetime.fromtimestamp(posted_ts, TAIPEI) if posted_ts is not None else None
    edit_ok = (edit is not None and edit <= detected_at
               and (posted is None or posted <= edit)
               and (previous is None or previous < edit))
    occurred_at = edit if edit_ok else detected_at
    event_time = now_str()  # 保留 events.csv 原有的偵測時間格式與語意
    path = os.path.join(os.path.dirname(EVENTS_FILE), "price_event_times.csv")
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    # 先保存時間依據再寫主事件；網站只連結已有主事件的紀錄，忽略未完成的寫入。
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PRICE_EVENT_FIELDS)
        if new:
            w.writeheader()
        w.writerow({"time": event_time, "source_url": url, "detail": detail,
                    "occurred_at": occurred_at.isoformat(), "detected_at": detected_at.isoformat(),
                    "time_basis": "ptt_edit" if edit_ok else "detected"})
    log_event(url, "價格變動", detail, event_time=event_time)


MAX_CHECK_GAP_DAYS = 3  # 兩次檢查間隔超過這麼久，售出天數誤差太大，不採計


def _parse_time(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def set_days_to_sell(row, prev_checked="", last_edit=None):
    """
    售出天數：
    - 觀測：上次檢查時還在賣（且間隔不超過 MAX_CHECK_GAP_DAYS），這次才看到售出。
      若最後編輯時間落在兩次檢查之間，用編輯時間，否則用這次檢查時間。
    - 推估：第一次看到就已售出，或間隔太久；用最後一次編輯文章的時間（賣家通常在賣掉時改標題）。
    - 無法推估：文章沒有編輯紀錄。
    """
    now = datetime.now()
    posted, last = _parse_time(row.get("post_time")), _parse_time(prev_checked)
    row["days_to_sell"], row["days_to_sell_basis"] = "", BASIS_UNKNOWN
    if posted is None:
        return
    edit_ok = last_edit is not None and posted < last_edit <= now
    if last is not None and (now - last).days <= MAX_CHECK_GAP_DAYS:
        sold_at = last_edit if edit_ok and last_edit > last else now
        basis = BASIS_OBSERVED
    elif edit_ok:
        sold_at, basis = last_edit, BASIS_ESTIMATED
    else:
        return
    row["days_to_sell"] = round((sold_at - posted).total_seconds() / 86400, 1)
    row["days_to_sell_basis"] = basis


def mark_status(row, status, prev_checked="", last_edit=None):
    """更新狀態；第一次偵測到已售出時記錄時間與銷售天數。"""
    old = row.get("status") or STATUS_ACTIVE
    if status == old:
        return
    row["status"] = status
    if status == STATUS_SOLD and not row.get("sold_detected_at"):
        row["sold_detected_at"] = now_str()
        set_days_to_sell(row, prev_checked, last_edit)
    log_event(row["source_url"], "狀態變更", f"{old} → {status}")


def needs_days_backfill(row):
    """舊版留下的已售出資料：沒有 basis，或售出天數是「第一次看到就已售出」時誤算的。"""
    return row.get("status") == STATUS_SOLD and not row.get("days_to_sell_basis")


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
def process_article(url, listings, use_llm, stats, multi=None):
    code, html = fetch(url)
    row = listings.get(url)
    if code == 404:
        if row and needs_days_backfill(row):
            row["days_to_sell"], row["days_to_sell_basis"] = "", BASIS_UNKNOWN
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
    checked_at = taipei_now()
    h = body_hash(art["body"])
    status = detect_status(art["title"], art["body"])
    price_confirmed = bool(row and row.get("body_hash") == h)

    first_seen = None
    skipped_row = None
    if REPARSE and use_llm and row is not None and row.get("status") == "略過":
        prev = skipped_from(url) if row.get("model") else None
        if prev and safe_extract(art, stats) is not None:
            # 先前被「排除誤判」改成略過、現在規則認得的文章：恢復原本狀態，保留售出天數等紀錄
            row["status"] = prev
            log_event(url, "恢復誤排除", f"略過 → {prev}")
        else:
            # 規則改進後，先前略過的文章當成新文章重新判斷，但保留第一次看到的時間
            first_seen = row.get("first_seen")
            skipped_row = listings.pop(url)
            row = None

    if row is None:
        if not use_llm:
            return  # 新文章要等有 LLM 時才解析
        print("    [NEW] 新文章，解析欄位。")
        fields = safe_extract(art, stats)
        if fields is None and art.get("extract_failed"):
            # Claude 暫時失敗：不記成略過（略過列之後不回訪），留給下次重新萃取
            if skipped_row is not None:
                listings[url] = skipped_row
            print("    [RETRY] 萃取失敗，下次再試。")
            return
        if multi is not None:
            if fields is None and record_multi(url, art, multi, first_seen):
                print(f"    [MULTI] 多品項文章，拆出 {len(multi[url])} 支 iPhone（只算刊登價）。")
            elif fields is not None:
                multi.pop(url, None)
        if fields is None:
            # 仍記錄 hash，避免每次重跑；status 標成「略過」不進行情統計
            listings[url] = {"source_url": url, "post_time": post_time_from_url(url), "title": art["title"],
                             "status": "略過", "first_seen": first_seen or now_str(), "last_checked": now_str(),
                             "body_hash": h}
            return
        row = {"source_url": url, "post_time": post_time_from_url(url), "first_seen": first_seen or now_str(),
               "status": STATUS_ACTIVE, "first_price": fields["price"], **fields}
        price_confirmed = True
        listings[url] = row
        stats["new"] += 1
        log_event(url, "新刊登", f"{fields['model']} {fields['storage']} ${fields['price']}")
    elif row.get("status") == "略過":
        row["last_checked"] = now_str()
        return
    elif use_llm and (row.get("body_hash") != h or REPARSE):
        edited = bool(row.get("body_hash")) and row["body_hash"] != h
        print("    [UPDATE] 本文被編輯，重新解析。" if edited else "    [REPARSE] 依新規則重新解析。")
        fields = safe_extract(art, stats)
        price_confirmed = fields is not None
        if fields is None and REPARSE and row.get("body_hash") == h and not_single_iphone(art):
            # 本文沒變、新規則判定是配件或一篇賣多支 → 不再當單支刊登計入
            log_event(url, "排除誤判", f"{row.get('status')} → 略過（重新解析）")
            row["status"] = "略過"
            if multi is not None:
                record_multi(url, art, multi, row.get("first_seen"))
            row["last_checked"] = now_str()
            return
        if fields:
            old_price = to_int(row.get("price"))
            if old_price and fields["price"] != old_price:
                if edited:
                    log_price_change(row, fields["price"], art["last_edit"], checked_at)
                    stats["price_changes"] += 1
                else:
                    # 本文沒變、只是舊規則抓錯：連首次標價一起更正，不記成價格變動
                    log_event(url, "重新解析修正", f"{old_price} → {fields['price']}")
                    if to_int(row.get("first_price")) == old_price:
                        row["first_price"] = fields["price"]
            if not fields.get("color"):
                fields["color"] = row.get("color", "")
            row.update(fields)

    # 新文章沒有上次檢查時間：第一次看到就已售出時，無從得知何時賣掉，不計售出天數
    prev_checked = row.get("last_checked", "")
    row["title"] = art["title"]
    # 解析失敗或僅查狀態時，不消耗尚未確認的本文改動與價格時間區間。
    if price_confirmed:
        row["body_hash"] = h
    row["last_checked"] = now_str()
    row["last_edit_at"] = (art["last_edit"].replace(tzinfo=TAIPEI).isoformat()
                           if art["last_edit"] is not None else "")
    if price_confirmed:
        row["price_checked_at"] = checked_at.isoformat()
    before = row.get("status")
    if before == STATUS_SOLD and needs_days_backfill(row):
        if row.get("days_to_sell") not in ("", None) and not sold_on_first_sight(row):
            row["days_to_sell_basis"] = BASIS_OBSERVED
        else:
            set_days_to_sell(row, "", art["last_edit"])
    mark_status(row, status, prev_checked, art["last_edit"])
    if row["status"] in OPEN_STATUSES:
        row["private_msg_count"] = art["pm_count"]
    if status == STATUS_SOLD and before != STATUS_SOLD:
        stats["sold"] += 1


EXTRACTOR = "rules"
REPARSE = False  # --reparse：追蹤期內所有文章都用目前的規則重新萃取


def safe_extract(art, stats):
    title, body = art["title"], art["body"]
    try:
        if EXTRACTOR == "ollama":
            fields = build_fields(llm_extract(title, body))
            return fields and {**fields, "extractor": "ollama"}
        fields = build_fields(rule_extract(title, body))
        if fields is not None:
            return {**fields, "extractor": "rules"}
        # 規則抓不到（賣家沒照範本寫）才問 Claude；配件文、一篇賣多支照舊略過
        if EXTRACTOR != "claude" or not_single_iphone(art):
            return None
        try:
            parsed = claude_extract(title, body)
        except Exception:
            art["extract_failed"] = True  # 與「確定不是單支 iPhone」區分，新文章不寫成略過
            raise
        fields = build_fields(parsed)
        stats["claude"] = stats.get("claude", 0) + 1
        if fields is None:
            return None
        print(f"    [CLAUDE] 規則抓不到，由 Claude 萃取：{fields['model']} {fields['storage']} ${fields['price']}")
        return {**fields, "color": parse_color(fields["model"], re.sub(r"^\[[^\]]*\]\s*", "", title)) or "",
                "extractor": "claude"}
    except Exception as e:
        print(f"    [ERR] 解析失敗：{e}")
        stats["errors"] += 1
        return None


# ==========================================
# 第四階段：行情彙整
# ==========================================
def sold_on_first_sight(row):
    """舊版會替「第一次看到就已售出」的文章算售出天數；這類資料不採計。"""
    try:
        first = datetime.strptime(row["first_seen"], "%Y-%m-%d %H:%M:%S")
        sold = datetime.strptime(row["sold_detected_at"], "%Y-%m-%d %H:%M:%S")
    except (KeyError, ValueError):
        return False
    return abs((sold - first).total_seconds()) < 600


def median(xs):
    return int(statistics.median(xs)) if xs else ""


def build_summary(listings, path=None, multi=None):
    path = path or SUMMARY_FILE
    groups = {}
    # 多品項文章拆出的 iPhone 只算刊登價：計入刊登數與價格，不計售出
    for items in (multi or {}).values():
        for r in items:
            price = to_int(r.get("price"))
            if price and r.get("model"):
                key = (r["model"], r.get("storage", ""), r.get("全新未拆封機", "否"))
                groups.setdefault(key, []).append(({**r, "status": MULTI_STATUS}, price))
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
        n_multi = sum(1 for r, _ in items if r["status"] == MULTI_STATUS)
        days, n_obs, n_est = [], 0, 0
        for r, _ in sold:
            if r.get("days_to_sell") in ("", None):
                continue
            basis = r.get("days_to_sell_basis")
            if basis == BASIS_ESTIMATED:
                n_est += 1
            elif basis == BASIS_OBSERVED or (not basis and not sold_on_first_sight(r)):
                n_obs += 1
            else:
                continue
            days.append(float(r["days_to_sell"]))
        batt = [to_int(r.get("battery_health")) for r, _ in items if to_int(r.get("battery_health"))]
        rows.append({
            "model": model, "storage": storage, "全新未拆封機": new,
            "刊登數": len(items),
            "已售出數": len(sold),
            # 多品項文章無法判斷是哪一支售出，售出率只用單支刊登的文章計算
            "售出率": f"{len(sold) / (len(items) - n_multi):.0%}" if len(items) > n_multi else "",
            "刊登價中位數": median(prices),
            "成交價中位數(已售標價)": median([p for _, p in sold]),
            "最低價": min(prices), "最高價": max(prices),
            "平均電池": round(sum(batt) / len(batt)) if batt else "",
            "售出天數中位數": round(statistics.median(days), 1) if days else "",
            "售出天數樣本(觀測/推估)": f"{n_obs}/{n_est}" if days else "",
            "多品項刊登數": n_multi,
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
    ap.add_argument("--max-pages", type=int, default=50, help="掃描看板最多翻幾頁（預設 50）")
    ap.add_argument("--track-days", type=int, default=45, help="在售文章發文後持續回訪幾天（預設 45）")
    ap.add_argument("--extractor", choices=["auto", "rules", "claude", "ollama"], default="auto",
                    help="欄位萃取方式：rules＝只用發文範本規則；claude＝規則抓不到時改問 Claude（需 ANTHROPIC_API_KEY）；"
                         "ollama＝本機 LLM；auto（預設）＝有 ANTHROPIC_API_KEY 用 claude，否則 rules")
    ap.add_argument("--no-llm", "--track-only", dest="no_llm", action="store_true",
                    help="不解析新文章，只回訪既有文章更新狀態")
    ap.add_argument("--report-only", action="store_true", help="只重算行情彙整")
    ap.add_argument("--reparse", action="store_true",
                    help="萃取規則改過後使用：追蹤期內所有文章（含已售出、略過）重新萃取欄位")
    ap.add_argument("--migrate", metavar="V1_CSV", help="匯入 v1 的 macshop_raw_data.csv")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    listings = load_listings()
    multi = load_multi()
    if args.migrate:
        migrate(args.migrate, listings)
        save_listings(listings)

    if not args.report_only and not args.migrate:
        stats = {"new": 0, "sold": 0, "deleted": 0, "price_changes": 0, "errors": 0, "claude": 0}
        use_llm = not args.no_llm  # 是否解析新文章／被編輯的文章
        global EXTRACTOR, REPARSE
        EXTRACTOR = args.extractor
        if EXTRACTOR == "auto":
            EXTRACTOR = "claude" if os.environ.get("ANTHROPIC_API_KEY") else "rules"
        print(f"[INFO] 欄位萃取：{EXTRACTOR}")
        REPARSE = args.reparse

        print("=" * 60 + "\n[INFO] 第一階段：掃描看板\n" + "=" * 60)
        targets = [] if not use_llm else scan_board(args.days, args.max_pages)
        print(f"[INFO] 看板上找到 {len(targets)} 篇 iPhone 販售文。")

        track_cutoff = (datetime.now() - timedelta(days=args.track_days)).timestamp()
        revisit_statuses = OPEN_STATUSES | ({STATUS_SOLD, "略過"} if args.reparse else set())
        revisit = [u for u, r in listings.items()
                   if r.get("status") in revisit_statuses and (url_timestamp(u) or 0) >= track_cutoff]
        backfill = [u for u, r in listings.items() if needs_days_backfill(r)]
        queue = list(dict.fromkeys([t["link"] for t in targets] + revisit + backfill))
        print(f"[INFO] 另有 {len(revisit)} 篇在售文章需回訪、{len(backfill)} 篇已售出文章補算售出天數，"
              f"合計處理 {len(queue)} 篇。")

        print("=" * 60 + "\n[INFO] 第二、三階段：解析新文章 + 回訪追蹤\n" + "=" * 60)
        for i, url in enumerate(queue, 1):
            print(f"\n[{i}/{len(queue)}] {url}")
            try:
                process_article(url, listings, use_llm, stats, multi)
            except Exception as e:
                print(f"    [ERR] {e}")
                stats["errors"] += 1
            if i % 10 == 0:
                save_listings(listings)  # 中途存檔，被中斷也不會白跑
                save_multi(multi)
            polite_sleep()
        save_listings(listings)
        save_multi(multi)
        print("\n" + "=" * 60)
        print(f"[DONE] 新刊登 {stats['new']}｜新售出 {stats['sold']}｜刪文 {stats['deleted']}"
              f"｜價格變動 {stats['price_changes']}｜錯誤 {stats['errors']}｜Claude 萃取 {stats['claude']}")

    dropped = drop_misparsed(listings)
    colored = backfill_colors(listings)
    if colored:
        print(f"[COLOR] {colored} 篇由既存標題補上顏色")
    if dropped:
        print(f"[CLEAN] {dropped} 篇誤判（配件、不存在的型號）改為略過")
    if dropped or colored:
        save_listings(listings)
    rows = build_summary(listings, multi=multi)
    print(f"[REPORT] 行情彙整 {len(rows)} 組 → {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
