"""日本買取價時間序列。--dry-run 只印結果，不建立或修改任何 CSV。"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from curl_cffi import requests

TOKYO = ZoneInfo("Asia/Tokyo")
KEY = ["shop", "model", "storage", "condition", "carrier", "color"]
PRICE_FIELDS = KEY + ["price_jpy", "observed_at", "shop_updated", "source_url"]
LATEST_FIELDS = KEY + ["price_jpy", "since", "last_checked", "shop_updated", "source_url"]
RUN_FIELDS = ["run_at", "shop", "status", "rows", "error"]
DEFAULT_DATA = Path(__file__).resolve().parents[1] / "data" / "jp"
MOBILEMIX_URL = "https://mobile-mix.jp/?category=7"
# 每頁只收該頁機型的列；アメモバ曾在 17 Pro 頁混入 Air 的列。
IOSYS_PAGES = {
    "https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone18-pro/": "iPhone 18 Pro",
    "https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone18-pro-max/": "iPhone 18 Pro Max",
    "https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone17pro/": "iPhone 17 Pro",
    "https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone17pro_max/": "iPhone 17 Pro Max",
    "https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone17/": "iPhone 17",
    "https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone_air/": "iPhone Air",
}
AMEMOBA_PAGES = {
    "https://amemoba.com/smartphone/iphone/iphone-18-pro/": "iPhone 18 Pro",
    "https://amemoba.com/smartphone/iphone/iphone-18pro-max/": "iPhone 18 Pro Max",
    "https://amemoba.com/smartphone/iphone/iphone-17-pro/": "iPhone 17 Pro",
    "https://amemoba.com/smartphone/iphone/iphone-17pro-max/": "iPhone 17 Pro Max",
    "https://amemoba.com/smartphone/iphone/iphone-17/": "iPhone 17",
    "https://amemoba.com/smartphone/iphone/iphoneair/": "iPhone Air",
}
IOSYS_URLS, AMEMOBA_URLS = tuple(IOSYS_PAGES), tuple(AMEMOBA_PAGES)

class ParseError(ValueError):
    """結構或筆數不可信；不得把舊價格誤記為下架。"""


def normalized(text):
    return unicodedata.normalize("NFKC", text).strip()


# 追蹤的機型；17e、16 以前、iPad 等都不收。容量以店家頁面實際有的為準。
MODELS = ("iPhone 17", "iPhone Air", "iPhone 17 Pro", "iPhone 17 Pro Max", "iPhone 18 Pro", "iPhone 18 Pro Max")
STORAGES = ("256GB", "512GB", "1TB", "2TB")


def model_storage(text):
    text = normalized(text)
    m = re.search(r"iPhone\s*(?:(1[78])\s*Pro(\s*Max)?|(17)|(?:17\s*)?(Air))\s*"
                  r"(256\s*GB|512\s*GB|1\s*TB|2\s*TB)\b", text, re.I)
    if not m:
        return None
    if m[1]:
        model = f"iPhone {m[1]} Pro" + (" Max" if m[2] else "")
    else:
        model = "iPhone 17" if m[3] else "iPhone Air"
    return model, re.sub(r"\s", "", m[5]).upper()


def carrier_name(text):
    text = normalized(text)
    if "海外版" in text:
        return None  # 海外版不是日本 SIMフリー，價格差很多，不收。
    for pattern, name in [(r"docomo|ドコモ", "docomo"), (r"SoftBank|ソフトバンク", "SoftBank"),
                          (r"Rakuten|楽天", "Rakuten"), (r"\bau\b|au版", "au")]:
        if re.search(pattern, text, re.I):
            return name
    if re.search(r"国内版\s*SIMフリー|SIMフリー", text):
        return "SIMフリー"
    return None


def page_date(soup):
    tagged = soup.select_one("#h1_date time[datetime]")
    if tagged:
        try:
            return datetime.fromisoformat(tagged["datetime"]).date().isoformat()
        except ValueError:
            pass
    text = soup.get_text(" ", strip=True)
    match = re.search(r"(?:更新日|更新日時|最終更新|価格更新)[：:\s]*(\d{4})[年/.-](\d{1,2})[月/.-](\d{1,2})", text)
    if match:
        try:
            return datetime(*map(int, match.groups())).date().isoformat()
        except ValueError:
            pass
    return ""


def make_row(shop, spec, condition, carrier, price, url, updated, color=""):
    return dict(zip(KEY, [shop, *spec, condition, carrier, color]),
                price_jpy=price, shop_updated=updated, source_url=url)


# 純 HTML parser 在下方定義；不讀時鐘、不連網、不寫檔。


def yen(node):
    if node is None:
        raise ParseError("價格元素消失")
    text = normalized(node.get_text(" ", strip=True))
    if re.search(r"買取不可|買取停止|買取終了|査定不可", text):
        return None
    values = re.findall(r"(?<![\d,])(?:\d{1,3}(?:,\d{3})+|\d+)\s*(?=円|$|[〜～])", text)
    if not values:
        raise ParseError(f"價格格式不明：{text[:100]}")
    price = max(int(v.replace(",", "")) for v in values)
    return price if price > 0 else None


def parse_mobilemix(html):
    soup = BeautifulSoup(html, "html.parser")
    updated, rows = page_date(soup), []
    for tr in soup.select("table.list tr[id]"):
        product = tr.select_one("td.product")
        spec = model_storage(product.get_text(" ", strip=True)) if product else None
        if not spec:
            continue
        detail = tr.find_next_sibling("tr")
        state = detail.select_one("td.open") if detail else None
        if state is None:
            raise ParseError("mobile-mix 商品狀態列消失")
        if "未開封" not in state.get_text():
            continue
        price = yen(tr.select_one("td.price"))
        if price is None:
            continue
        condition_node = state.find_next_sibling("td")
        terms = normalized(condition_node.get_text(" ", strip=True)) if condition_node else ""
        inputs = detail.select("td.cart input.colorCircle")
        colors = []
        for item in inputs:
            label = item.find_parent("label") or detail.find("label", attrs={"for": item.get("id")})
            if label is None or not re.fullmatch(r"-?\d+", item.get("value", "")):
                raise ParseError("mobile-mix 顏色或減價欄位消失")
            colors.append((label.get_text(" ", strip=True), int(item["value"])))
        # 只檢查條件欄，不讓表單的其他文字干擾「のみ」或「買取不可」。
        only = terms.split("のみ", 1)[0] if "のみ" in terms and "他色買取不可" in terms else None
        banned = set()
        for clause in re.findall(r"([^、,;。\s]*?)買取不可", terms):
            banned.update(color for color, _ in colors if color in clause)
        rows.append(make_row("mobile-mix", spec, "未開封", "SIMフリー", price, MOBILEMIX_URL, updated))
        for color, delta in colors:
            if color in banned or (only is not None and color not in only):
                continue
            if price + delta <= 0:
                raise ParseError("mobile-mix 色價非正數")
            rows.append(make_row("mobile-mix", spec, "未開封", "SIMフリー", price + delta,
                                 MOBILEMIX_URL, updated, color))
    return rows, updated


def parse_iosys(html, url):
    soup = BeautifulSoup(html, "html.parser")
    updated, rows = page_date(soup), []
    for tr in soup.select("tr[data-group-id]"):
        name, carrier = tr.select_one(".name"), tr.select_one(".carrer")
        spec = model_storage(name.get_text(" ", strip=True)) if name else None
        version = carrier_name(carrier.get_text(" ", strip=True)) if carrier else None
        if not spec or not version:
            continue
        for selector, condition in [(".s-price", "未開封"), (".a-price", "中古上限")]:
            price = yen(tr.select_one(selector))
            if price is not None:
                rows.append(make_row("イオシス", spec, condition, version, price, url, updated))
    return rows, updated


def parse_amemoba(html, url):
    soup = BeautifulSoup(html, "html.parser")
    updated, rows = page_date(soup), []
    for tr in soup.select("tr.p-purchaseArchive__tableRow"):
        name, carrier = tr.select_one(".p-purchaseArchive__termName"), tr.select_one(".p-purchaseArchive__termCarrier")
        spec = model_storage(name.get_text(" ", strip=True)) if name else None
        version = carrier_name(carrier.get_text(" ", strip=True)) if carrier else None
        if not spec or not version:
            continue
        for selector, condition in [(".p-purchaseArchive__priceNew", "未開封"),
                                    (".p-purchaseArchive__priceOld", "中古上限")]:
            block = tr.select_one(selector)
            if block is None:
                raise ParseError("アメモバ 價格區塊消失")
            label = block.select_one("dt")
            expected = r"未開封|新品" if condition == "未開封" else "中古"
            if not label or not re.search(expected, label.get_text()):
                raise ParseError("アメモバ 商品狀態格式不明")
            price = yen(block.select_one("dd"))
            if price is not None:
                rows.append(make_row("アメモバ", spec, condition, version, price, url, updated))
    return rows, updated


_last_request = None
_host_requests = {}


def fetch(url):
    """所有請求（含重試）序列化；全域至少 5 秒、イオシス同站至少 60 秒。"""
    global _last_request
    host = urlparse(url).hostname
    for attempt in range(2):
        now = time.monotonic()
        wait = max(0, 5 - (now - _last_request)) if _last_request is not None else 0
        if host == "k-tai-iosys.com" and host in _host_requests:
            wait = max(wait, 60 - (now - _host_requests[host]))
        if wait > 0:
            time.sleep(wait)
        _last_request = _host_requests[host] = time.monotonic()
        try:
            response = requests.get(url, impersonate="chrome",
                                    headers={"Accept-Language": "ja-JP,ja;q=0.9"}, timeout=45)
            response.raise_for_status()
            return response.text
        except requests.RequestsError:
            if attempt:
                raise


def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def row_key(row):
    return tuple(row.get(k, "") for k in KEY)


def append_csv(path, fields, rows):
    if not rows:
        return
    header = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        if header:
            writer.writeheader()
        writer.writerows(rows)


def validate_rows(shop, rows, previous):
    unique = {}
    for row in rows:
        if (row.get("shop") != shop or row.get("model") not in MODELS or row.get("storage") not in STORAGES
                or row.get("condition") not in ("未開封", "中古上限")
                or row.get("carrier") not in ("SIMフリー", "docomo", "au", "SoftBank", "Rakuten")
                or not isinstance(row.get("price_jpy"), int) or row["price_jpy"] <= 0):
            raise ParseError("規格或價格欄位不合法")
        key = row_key(row)
        if key in unique and unique[key]["price_jpy"] != row["price_jpy"]:
            raise ParseError("同規格出現互相矛盾的價格")
        unique[key] = row
    if not unique or (previous and len(unique) * 2 <= len(previous)):
        raise ParseError(f"筆數防呆：本次 {len(unique)}，上次 {len(previous)}")
    return unique


def apply_results(data_dir, results, run_at=None):
    """每店獨立驗證與更新；失敗店保留 latest、prices，只有 runs 記失敗。"""
    data_dir = Path(data_dir)
    run_at = run_at or datetime.now(TOKYO).isoformat(timespec="seconds")
    dt = datetime.fromisoformat(run_at)
    if dt.tzinfo is None:
        raise ValueError("run_at 必須帶時區")
    run_at = dt.astimezone(TOKYO).isoformat(timespec="seconds")
    latest = {row_key(r): r for r in read_csv(data_dir / "latest.csv")}
    history = {row_key(r): r for r in read_csv(data_dir / "prices.csv")}
    events, runs = [], []
    any_ok = False
    for result in results:
        shop, status = result["shop"], result.get("status", "ok")
        rows, error = result.get("rows", []), result.get("error", "")
        previous = {k: r for k, r in latest.items() if r["shop"] == shop}
        if status == "ok":
            try:
                current = validate_rows(shop, rows, previous)
            except ParseError as exc:
                status, error = "parse_error", str(exc)
        if status == "ok":
            any_ok = True
            for key, row in current.items():
                old = history.get(key)
                changed = old is None or str(old["price_jpy"]) != str(row["price_jpy"])
                if changed:
                    events.append({**row, "observed_at": run_at})
                since = run_at if changed else previous.get(key, {}).get("since", old["observed_at"])
                latest[key] = {**row, "since": since, "last_checked": run_at}
            # 以最後歷史列為準，也能從 latest 缺失的中斷執行恢復。
            active = {k: r for k, r in history.items() if r["shop"] == shop and r["price_jpy"] != ""}
            active.update(previous)
            for key, old in active.items():
                if key not in current:
                    events.append({**{f: old.get(f, "") for f in PRICE_FIELDS},
                                   "price_jpy": "", "observed_at": run_at,
                                   "shop_updated": result.get("shop_updated", "")})
                    latest.pop(key, None)
        runs.append(dict(run_at=run_at, shop=shop, status=status, rows=len(rows), error=error))
    data_dir.mkdir(parents=True, exist_ok=True)
    append_csv(data_dir / "prices.csv", PRICE_FIELDS, events)
    if any_ok:
        temporary = data_dir / "latest.csv.tmp"
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=LATEST_FIELDS)
            writer.writeheader()
            writer.writerows(latest[k] for k in sorted(latest))
        temporary.replace(data_dir / "latest.csv")
    append_csv(data_dir / "runs.csv", RUN_FIELDS, runs)
    return runs


def collect(fetcher=None):
    fetcher = fetcher or fetch
    shops = [("mobile-mix", [MOBILEMIX_URL], lambda html, url: parse_mobilemix(html)),
             ("イオシス", IOSYS_URLS, parse_iosys), ("アメモバ", AMEMOBA_URLS, parse_amemoba)]
    results = []
    for shop, urls, parser in shops:
        rows, dates, status, error = [], [], "ok", ""
        for url in urls:
            try:
                html = fetcher(url)
            except Exception as exc:
                status, error = "fetch_error", f"{url}: {type(exc).__name__}: {exc}"
                break
            try:
                parsed, updated = parser(html, url)
                page_model = {**IOSYS_PAGES, **AMEMOBA_PAGES}.get(url)
                if page_model:
                    parsed = [r for r in parsed if r["model"] == page_model]
                if not parsed:
                    raise ParseError(f"頁面解析 0 筆：{url}")
                rows.extend(parsed)
                if updated:
                    dates.append(updated)
            except (ValueError, TypeError, KeyError) as exc:
                status, error = "parse_error", str(exc)
                break
        results.append(dict(shop=shop, status=status, rows=rows, error=error,
                            shop_updated=max(dates, default="")))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="日本 CSV 目錄（不讀寫台灣 CSV）")
    parser.add_argument("--dry-run", action="store_true", help="只印解析結果，完全不寫 CSV")
    args = parser.parse_args()
    results = collect()
    if args.dry_run:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(apply_results(args.data, results), ensure_ascii=False, indent=2))
    return 0 if all(r["status"] == "ok" for r in results) else 1 if args.dry_run else 0


if __name__ == "__main__":
    raise SystemExit(main())
