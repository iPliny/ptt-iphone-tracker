"""PTT 每日交易觀測：把 data/ 的 CSV 整理成網站用的 data.json，並複製靜態檔到輸出目錄。

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
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DIR = os.path.join(ROOT, "site")
DATA_DIR = os.path.join(ROOT, "data")
STATIC_FILES = ["index.html", "model.html", "common.js", "app.js", "model.js", "watchlist.js", "style.css",
                "prices.html", "prices.js", "prices.css", "official-prices.json"]
CSV_FILES = ["listings.csv", "events.csv", "market_summary.csv", "price_event_times.csv"]
TAIPEI = timezone(timedelta(hours=8))

TRACKED_STATUSES = {"在售", "交易中", "已售出", "已刪除"}
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


def build_data(data_dir=DATA_DIR, now=None):
    raw = read_csv(os.path.join(data_dir, "listings.csv"))
    events = read_csv(os.path.join(data_dir, "events.csv"))
    events = attach_price_times(events, read_csv(os.path.join(data_dir, "price_event_times.csv")))
    listings = [clean_listing(r) for r in raw if r.get("status") in TRACKED_STATUSES]
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
        "models": model_stats(listings),
        "model_totals": model_totals(listings),
        "summary": read_csv(os.path.join(data_dir, "market_summary.csv")),
        "listings": listings,
        "events": events_out,
    }


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
    return data


def main():
    ap = argparse.ArgumentParser(description="建置 PTT 每日交易觀測網站")
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"), help="輸出目錄（預設 _site/）")
    ap.add_argument("--data", default=DATA_DIR, help="CSV 所在目錄（預設 data/）")
    args = ap.parse_args()
    data = build(args.out, args.data)
    print(f"[SITE] 已輸出到 {args.out}：{data['counts']['total']} 篇、{len(data['days'])} 天、{len(data['events'])} 筆事件")


if __name__ == "__main__":
    main()
