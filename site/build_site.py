"""PTT MacShop交易觀測：把 data/ 的 CSV 整理成網站用的 data.json，並複製靜態檔到輸出目錄。

只用標準函式庫，不需網路。執行：
    python site/build_site.py            # 輸出到 _site/
    python site/build_site.py --out dist
預覽：
    python -m http.server -d _site 8000
"""
import argparse
import csv
import json
import os
import shutil
import statistics
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlencode
from xml.sax.saxutils import escape
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(ROOT, "data")
STATIC_FILES = ["index.html", "model.html", "common.js", "app.js", "model.js", "watchlist.js", "style.css",
                "prices.html", "prices.js", "prices.css", "official-prices.json"]
CSV_FILES = ["listings.csv", "events.csv", "market_summary.csv", "price_event_times.csv", "multi_items.csv"]
TAIPEI = timezone(timedelta(hours=8))
SITE_URL = "https://ipliny.github.io/ptt-iphone-tracker/"  # sitemap.xml 用的正式網址

TRACKED_STATUSES = {"在售", "交易中", "已售出", "已刪除"}
MULTI_STATUS = "多品項"  # 一篇賣多支時拆出的 iPhone：只算刊登數與刊登價
MAX_DAYS = 90       # 每日序列最多保留幾天
MAX_EVENTS = 1000   # 網頁上最多帶幾筆事件


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def to_int(value):
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return None


def to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def day_of(ts):
    """'2026-03-26 18:16:25' → '2026-03-26'；格式不對回傳 None。"""
    ts = (ts or "").strip()
    try:
        return datetime.strptime(ts[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def sold_time(r):
    """售出時間：有售出天數（觀測或推估）就用發文時間加天數，否則退回偵測到售出的時間。"""
    days = to_float(r.get("days_to_sell"))
    try:
        posted = datetime.strptime((r.get("post_time") or "").strip(), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        posted = None
    if days is not None and posted is not None:
        return (posted + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    return r.get("sold_detected_at", "")


def clean_listing(r):
    sold = r.get("status") == "已售出"
    return {
        "url": r.get("source_url", ""),
        "post_time": r.get("post_time", ""),
        "title": r.get("title", ""),
        "status": r.get("status", ""),
        "model": r.get("model", ""),
        "storage": r.get("storage", ""),
        "color": r.get("color", ""),
        "brand_new": r.get("全新未拆封機", "") == "是",
        "battery": to_int(r.get("battery_health")),
        "price": to_int(r.get("price")),
        "pm_count": to_int(r.get("private_msg_count")),
        "first_price": to_int(r.get("first_price")),
        "warranty": r.get("warranty", ""),
        "notes": r.get("notes", ""),
        "sold_at": sold_time(r) if sold else "",
        "sold_detected_at": r.get("sold_detected_at", ""),
        "days_to_sell": to_float(r.get("days_to_sell")),
        "days_basis": r.get("days_to_sell_basis", ""),  # 觀測／推估／無法推估；舊資料為空
        "first_seen": r.get("first_seen", ""),
        "last_checked": r.get("last_checked", ""),
        "last_edit_at": r.get("last_edit_at", ""),
    }


def load_multi_items(data_dir):
    """multi_items.csv 的每支 iPhone，轉成和 clean_listing 相同的格式（狀態固定為「多品項」）。"""
    return [clean_listing({**r, "status": MULTI_STATUS})
            for r in read_csv(os.path.join(data_dir, "multi_items.csv"))]


def load_priced(raw, data_dir):
    """單支刊登與多品項拆出的 iPhone 一起剔除異常價格；回傳 (單支刊登, 多品項)。"""
    listings = [clean_listing(r) for r in raw if r.get("status") in TRACKED_STATUSES]
    multi = load_multi_items(data_dir)
    drop_price_outliers(listings + multi)
    return listings, multi


OUTLIER_MIN_SAMPLES = 5   # 同組至少幾筆才判斷價格是否異常
OUTLIER_LOW, OUTLIER_HIGH = 0.5, 2.0  # 低於中位數一半、高於兩倍視為抓錯


def price_outliers(listings):
    """明顯不合理的價格（多半是把日期、保固期限抓成售價）：回傳 [(文章, 參考中位數)]。
    先和同型號、同容量、同為全新或二手的中位數比；那組不到 5 筆時改和同型號比。"""
    def medians(key):
        groups = {}
        for r in listings:
            if r["price"] and r["model"]:
                groups.setdefault(key(r), []).append(r["price"])
        return {k: statistics.median(v) for k, v in groups.items() if len(v) >= OUTLIER_MIN_SAMPLES}

    fine = medians(lambda r: (r["model"], r["storage"], r["brand_new"]))
    coarse = medians(lambda r: (r["model"], r["brand_new"]))
    out = []
    for r in listings:
        if not (r["price"] and r["model"]):
            continue
        med = fine.get((r["model"], r["storage"], r["brand_new"])) or coarse.get((r["model"], r["brand_new"]))
        if med and not (OUTLIER_LOW * med <= r["price"] <= OUTLIER_HIGH * med):
            out.append((r, med))
    return out


def drop_price_outliers(listings):
    """異常價格不公開：價格改為 None，不列入統計與圖表（紀錄見 write_outlier_report）。"""
    for r, _ in price_outliers(listings):
        r["price"] = None
    return listings


def implausible_price_change(e):
    """降幅超過一半或漲幅超過一倍的改價，多半是某次價格抓錯，不公開。"""
    if e.get("event") != "價格變動":
        return False
    try:
        a, b = (to_int(x) for x in (e.get("detail") or "").split("→"))
    except ValueError:
        return False
    return bool(a and b) and not (OUTLIER_LOW * a <= b <= OUTLIER_HIGH * a)


def attach_price_times(events, times):
    """只使用該次改價保存的時間；不能以 listings 最新編輯時間改寫舊事件。"""
    def key(row):
        return (row.get("time"), row.get("source_url"), row.get("detail"))

    snapshots = {key(row): row for row in times}
    out = []
    for original in events:
        e = dict(original)
        if e.get("event") == "價格變動":
            e.update(detected_at=e.get("time", ""), time_basis="detected")
            saved = snapshots.get(key(original), {})
            try:
                occurred = datetime.fromisoformat(saved.get("occurred_at", ""))
                detected = datetime.fromisoformat(saved.get("detected_at", ""))
                if (occurred.tzinfo is not None and detected.tzinfo is not None
                        and occurred <= detected and saved.get("time_basis") in ("ptt_edit", "detected")):
                    e.update(time=occurred.astimezone(TAIPEI).strftime("%Y-%m-%d %H:%M:%S"),
                             detected_at=detected.astimezone(TAIPEI).isoformat(),
                             time_basis=saved["time_basis"])
            except (TypeError, ValueError):
                pass  # 舊檔缺少時間快照或資料無效時，保留原偵測紀錄
        out.append(e)
    return out


def tracked_events(events, listings):
    """只留還在統計內的文章的事件；改成「略過」的配件、誤判文不出現在事件列表與改價統計。"""
    urls = {r["url"] for r in listings}
    return [e for e in events if e.get("source_url") in urls]


def deleted_dates(events):
    """從 events 找出每篇文章第一次被記為已刪除的日期。"""
    out = {}
    for e in events:
        if e.get("event") == "狀態變更" and (e.get("detail") or "").endswith("已刪除"):
            d = day_of(e.get("time"))
            url = e.get("source_url", "")
            if d and url not in out:
                out[url] = d
    return out


def daily_series(listings, events, max_days=MAX_DAYS):
    """每天的新刊登、售出、刪文、改價數，以及當天結束時仍在架上的數量。"""
    del_day = deleted_dates(events)
    per = {}

    def bump(d, key):
        if d:
            per.setdefault(d, {"new": 0, "sold": 0, "deleted": 0, "price_changes": 0})[key] += 1

    spans = []  # (上架日, 下架日或 None)
    for r in listings:
        posted = day_of(r["post_time"])
        bump(posted, "new")
        sold = day_of(r["sold_at"]) if r["status"] == "已售出" else None
        bump(sold, "sold")
        gone = sold
        if r["status"] == "已刪除":
            gone = del_day.get(r["url"])
            bump(gone, "deleted")
        if posted:
            spans.append((posted, gone))
    for e in events:
        if e.get("event") == "價格變動":
            bump(day_of(e.get("time")), "price_changes")

    if not per:
        return []
    first, last = min(per), max(per)
    start = max(date.fromisoformat(first), date.fromisoformat(last) - timedelta(days=max_days - 1))
    end = date.fromisoformat(last)
    out = []
    d = start
    while d <= end:
        key = d.isoformat()
        row = {"date": key, **per.get(key, {"new": 0, "sold": 0, "deleted": 0, "price_changes": 0})}
        row["on_shelf"] = sum(1 for p, g in spans if p <= key and (g is None or g > key))
        out.append(row)
        d += timedelta(days=1)
    return out


def group_stats(items):
    """一組刊登（已確定有價格）的價格與售出統計。"""
    prices = [r["price"] for r in items]
    sold = [r for r in items if r["status"] == "已售出"]
    timed = [r for r in sold if r["days_to_sell"] is not None]
    days = [r["days_to_sell"] for r in timed]
    return {
        "listed": len(items),
        "multi": sum(1 for r in items if r["status"] == MULTI_STATUS),
        "active": sum(1 for r in items if r["status"] in ("在售", "交易中")),
        "sold": len(sold),
        "median_price": int(statistics.median(prices)),
        "median_sold_price": int(statistics.median([r["price"] for r in sold])) if sold else None,
        "min_price": min(prices), "max_price": max(prices),
        "median_days": round(statistics.median(days), 1) if days else None,
        "days_estimated": sum(1 for r in timed if r["days_basis"] == "推估"),
        "days_samples": len(timed),
    }


def model_stats(listings):
    """各型號×容量（不分全新與否）在售／已售的價格統計，供網頁的型號篩選使用。"""
    groups = {}
    for r in listings:
        if r["price"] and r["model"]:
            groups.setdefault((r["model"], r["storage"]), []).append(r)
    return [{"model": model, "storage": storage, **group_stats(items)}
            for (model, storage), items in sorted(groups.items())]


def model_totals(listings):
    """各型號不分容量的合計統計，給機型頁的「全部容量」分頁使用。"""
    groups = {}
    for r in listings:
        if r["price"] and r["model"]:
            groups.setdefault(r["model"], []).append(r)
    return [{"model": model, **group_stats(items)} for model, items in sorted(groups.items())]


COLOR_MIN_SAMPLES = 3


def color_stats(listings):
    """接收已隱藏異常價格的單支文章；先依容量與新舊校正，再合併顏色。"""
    priced = [r for r in listings if r.get("price") and r["price"] > 0 and r.get("model")]
    groups = {}
    key = lambda r: (r["model"], r.get("storage", ""), r.get("brand_new", False))
    for r in priced:
        groups.setdefault(key(r), []).append(r["price"])
    medians = {k: statistics.median(v) for k, v in groups.items() if len(v) >= COLOR_MIN_SAMPLES}
    colors = {}
    for r in priced:
        if not r.get("color"):
            continue
        for storage in (r.get("storage", ""), None):
            colors.setdefault((r["model"], storage, r["color"]), []).append(r)
    out = []
    for (model, storage, color), rows in colors.items():
        ratios = [Decimal(str(r["price"])) / Decimal(str(medians[key(r)])) for r in rows if key(r) in medians]
        enough = len(ratios) >= COLOR_MIN_SAMPLES
        used = [r["price"] for r in rows if not r.get("brand_new")]
        relative = None
        if enough:
            relative = float((statistics.median(ratios) - 1).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP))
        out.append({"model": model, "storage": storage, "color": color,
                    "listed": len(rows), "sold": sum(r.get("status") == "已售出" for r in rows),
                    # 價格欄只看二手：全新機價格高，混在一起會讓全新比例高的顏色看起來比較貴
                    "median_price": int(statistics.median(used)) if enough and len(used) >= COLOR_MIN_SAMPLES else None,
                    "used": len(used),
                    "relative": (relative or 0.0) if enough else None, "samples": len(ratios)})
    return sorted(out, key=lambda r: (r["model"], r["storage"] or "", r["color"]))


APPLE_PRICES = os.path.join(SITE_DIR, "apple_prices.json")  # Apple 台灣官網價格（人工查詢）


def apple_prices(models, path=APPLE_PRICES):
    """機型頁的原廠資訊：官網還在賣的給購買連結與現行售價，停售的給停售前最後的官方售價。

    只回傳 models 裡有的機型；檔案裡沒有的機型不列。"""
    models = set(models)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        src = json.load(f)
    out = {}
    for model, info in src["on_sale"].items():
        out[model] = {"buy_url": info["url"], "prices": info["prices"], "checked_at": src["checked_at"]}
    for model, info in src["discontinued"].items():
        prices = {k: v for k, v in info["prices"].items() if v}
        if prices and model not in out:
            out[model] = {"prices": prices, "discontinued": info.get("discontinued", ""),
                          "sources": info.get("sources", [])}
    return {m: v for m, v in out.items() if m in models}


def build_data(data_dir=DATA_DIR, now=None):
    raw = read_csv(os.path.join(data_dir, "listings.csv"))
    events = read_csv(os.path.join(data_dir, "events.csv"))
    events = attach_price_times(events, read_csv(os.path.join(data_dir, "price_event_times.csv")))
    events = [e for e in events if not implausible_price_change(e)]
    listings, multi = load_priced(raw, data_dir)
    events = tracked_events(events, listings)
    listings.sort(key=lambda r: r["post_time"], reverse=True)

    counts = {s: 0 for s in ("在售", "交易中", "已售出", "已刪除")}
    for r in listings:
        counts[r["status"]] += 1
    checked = [r["last_checked"] for r in listings if r["last_checked"]]
    events_out = sorted(
        ({"time": e.get("time", ""), "url": e.get("source_url", ""),
          "event": e.get("event", ""), "detail": e.get("detail", ""),
          "detected_at": e.get("detected_at", ""), "time_basis": e.get("time_basis", "")} for e in events),
        key=lambda e: e["time"], reverse=True)[:MAX_EVENTS]

    return {
        "generated_at": (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
        "last_checked": max(checked) if checked else "",
        "counts": {"total": len(listings), **counts},
        "days": daily_series(listings, events),
        # 型號統計另外納入多品項文章拆出的 iPhone（只影響刊登數與刊登價）
        "models": model_stats(listings + multi),
        "model_totals": model_totals(listings + multi),
        "colors": color_stats(listings),
        "summary": read_csv(os.path.join(data_dir, "market_summary.csv")),
        "listings": listings,
        "events": events_out,
        "apple": apple_prices(r["model"] for r in listings + multi),
    }


OUTLIER_REPORT = "price_outliers.csv"
OUTLIER_FIELDS = ["kind", "source_url", "title", "model", "storage", "brand_new", "price", "reference", "detail", "time"]


def write_outlier_report(data_dir=DATA_DIR):
    """把目前不公開的異常價格與改價寫成 data/price_outliers.csv（只留紀錄，不放上網站）。回傳筆數。"""
    raw = read_csv(os.path.join(data_dir, "listings.csv"))
    listings = [clean_listing(r) for r in raw if r.get("status") in TRACKED_STATUSES] + load_multi_items(data_dir)
    by_url = {r["url"]: r for r in listings}
    rows = [{"kind": "刊登價", "source_url": r["url"], "title": r["title"], "model": r["model"],
             "storage": r["storage"], "brand_new": "是" if r["brand_new"] else "否", "price": r["price"],
             "reference": int(med), "detail": "", "time": r["post_time"]}
            for r, med in price_outliers(listings)]
    for e in read_csv(os.path.join(data_dir, "events.csv")):
        if implausible_price_change(e):
            r = by_url.get(e.get("source_url"), {})
            rows.append({"kind": "改價", "source_url": e.get("source_url", ""), "title": r.get("title", ""),
                         "model": r.get("model", ""), "storage": r.get("storage", ""),
                         "brand_new": "是" if r.get("brand_new") else "否", "price": "",
                         "reference": "", "detail": e.get("detail", ""), "time": e.get("time", "")})
    with open(os.path.join(data_dir, OUTLIER_REPORT), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=OUTLIER_FIELDS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def sitemap_xml(data, today=None, column_urls=()):
    """首頁、歷代官方價格頁、每個機型頁（model.html?m=...，和網站內連結相同），以及每週專欄的入口與各期。"""
    lastmod = (today or datetime.now(TAIPEI).date()).isoformat()
    urls = [SITE_URL, SITE_URL + "prices.html", SITE_URL + "jp/"] + [SITE_URL + "model.html?" + urlencode({"m": m["model"]}) for m in data["model_totals"]]
    if column_urls:
        urls += [SITE_URL + "column/"] + list(column_urls)
    items = "".join(f"  <url><loc>{escape(u)}</loc><lastmod>{lastmod}</lastmod></url>\n" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + items + "</urlset>\n")


def build(out_dir, data_dir=DATA_DIR):
    os.makedirs(out_dir, exist_ok=True)
    for name in STATIC_FILES:
        shutil.copy(os.path.join(SITE_DIR, name), os.path.join(out_dir, name))
    # 原始 CSV 也一起放上去，網頁提供下載
    os.makedirs(os.path.join(out_dir, "data"), exist_ok=True)
    for name in CSV_FILES:
        src = os.path.join(data_dir, name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(out_dir, "data", name))
    data = build_data(data_dir)
    with open(os.path.join(out_dir, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    from column import render_column  # column.py 也會 import 這個檔，放在這裡避免循環
    column_urls = render_column(out_dir, data_dir)
    from jp_build import build_jp
    build_jp(out_dir, data_dir)
    with open(os.path.join(out_dir, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap_xml(data, column_urls=column_urls))
    return data


def main():
    ap = argparse.ArgumentParser(description="建置 PTT MacShop交易觀測網站")
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"), help="輸出目錄（預設 _site/）")
    ap.add_argument("--data", default=DATA_DIR, help="CSV 所在目錄（預設 data/）")
    ap.add_argument("--outlier-report", action="store_true",
                    help="只把不公開的異常價格寫成 data/price_outliers.csv，不建置網站")
    args = ap.parse_args()
    if args.outlier_report:
        print(f"[SITE] 異常價格 {write_outlier_report(args.data)} 筆 → {OUTLIER_REPORT}")
        return
    data = build(args.out, args.data)
    print(f"[SITE] 已輸出到 {args.out}：{data['counts']['total']} 篇、{len(data['days'])} 天、{len(data['events'])} 筆事件")


if __name__ == "__main__":
    main()
