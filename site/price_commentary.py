"""匯出機型短評所需的公開事實，並檢查待刊登的純文字。"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from statistics import median
from urllib.parse import urlsplit

from model_pages import trend_pct

STAT_FIELDS = (
    "listed", "active", "sold", "multi", "median_price", "min_price", "max_price",
    "median_sold_price", "median_days", "days_samples", "days_estimated",
)
URL = re.compile(
    r"[a-z][a-z0-9+.-]*://|mailto:|www\.|"
    r"(?<![a-z0-9_-])(?:[a-z0-9-]+\.)+[a-z]{2,}(?![a-z0-9_-])",
    re.IGNORECASE | re.ASCII,
)


def is_apple_url(value):
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and (host == "apple.com" or host.endswith(".apple.com"))


def compile_facts(data, month, as_of):
    """沿用建置快照的統計，月度篇數與行情採截至 as_of 的日期。"""
    from build_site import day_of

    models = {}
    for row in data["model_totals"]:
        model = row["model"]
        facts = {key: row[key] for key in STAT_FIELDS}
        facts.update(
            capacities={}, monthly={"listed": 0, "sold": 0, "median_sold_price_by_storage": {}},
            first_post_date=None, last_post_date=None,
            insufficient_samples=row["listed"] < 10 or row["sold"] == 0,
        )
        if model in data["apple"]:
            apple = data["apple"][model]
            # 保留公開原廠價，連結只帶 Apple 官網。
            official = {key: apple[key] for key in ("prices", "checked_at", "discontinued") if key in apple}
            sources = [url for url in apple.get("sources", []) if is_apple_url(url)]
            if sources:
                official["sources"] = sources
            if is_apple_url(apple.get("buy_url", "")):
                official["buy_url"] = apple["buy_url"]
            facts["apple"] = official
        models[model] = facts

    for row in data["models"]:
        capacity = {key: row[key] for key in STAT_FIELDS}
        capacity["trends"] = {"used": None, "brand_new": None}
        models[row["model"]]["capacities"][row["storage"]] = capacity

    trends = data["trends"]
    if trends["start"]:
        start = date.fromisoformat(trends["start"])
        days = max(0, (date.fromisoformat(as_of) - start).days + 1)
        for row in trends["series"]:
            values = row["values"][:days]
            latest = next((i for i in range(len(values) - 1, -1, -1) if values[i] is not None), None)
            if latest is None:
                continue
            condition = "brand_new" if row["brand_new"] else "used"
            capacity = models[row["model"]]["capacities"][row["storage"]]
            capacity["trends"][condition] = {
                "date": (start + timedelta(days=latest)).isoformat(),
                "price": values[latest],
                "change_7d_pct": trend_pct(values, 7),
                "change_30d_pct": trend_pct(values, 30),
            }

    sold_prices = defaultdict(list)
    for row in data["listings"]:
        facts = models.get(row["model"])
        if facts is None:
            continue
        monthly = facts["monthly"]
        # 本月篇數與刊登日期只計單支文章。價格未公開的文章仍計篇數。
        posted = day_of(row["post_time"])
        if posted and posted <= as_of:
            facts["first_post_date"] = min(facts["first_post_date"] or posted, posted)
            facts["last_post_date"] = max(facts["last_post_date"] or posted, posted)
            if posted[:7] == month:
                monthly["listed"] += 1
        detected = day_of(row["sold_detected_at"])
        if row["status"] == "已售出" and detected and detected[:7] == month and detected <= as_of:
            monthly["sold"] += 1
            if row["price"]:
                sold_prices[row["model"], row["storage"]].append(row["price"])
    for (model, storage), prices in sold_prices.items():
        models[model]["monthly"]["median_sold_price_by_storage"][storage] = int(median(prices))
    return {"month": month, "as_of": as_of, "models": models}


def load_commentary(data_dir):
    """讀取短評稿，尚未供稿時回傳 None。"""
    try:
        with (Path(data_dir) / "commentary" / "price.json").open(encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return None


def iso_date(value):
    """確認日期存在，且使用 YYYY-MM-DD 格式。"""
    try:
        return date.fromisoformat(value).isoformat() == value
    except (TypeError, ValueError):
        return False


def validate(commentary, model_names):
    """回傳稿件格式、機型覆蓋率與文字規格的錯誤。"""
    if not isinstance(commentary, dict):
        return ["缺少短評稿或根節點不是 JSON 物件"]
    errors = []
    month = commentary.get("month")
    if not isinstance(month, str) or not iso_date(month + "-01"):
        errors.append("month 必須為有效的 YYYY-MM")
    if not iso_date(commentary.get("as_of")):
        errors.append("as_of 必須為有效的 YYYY-MM-DD")
    texts = commentary.get("models")
    if not isinstance(texts, dict):
        return errors + ["models 必須是機型對應文字的 JSON 物件"]
    for model in sorted(set(model_names) - texts.keys()):
        errors.append(f"{model} 缺少短評")
    for model, body in texts.items():
        if not isinstance(body, str):
            errors.append(f"{model} 的短評必須是文字")
            continue
        length = len("".join(body.split()))
        if not 250 <= length <= 300:
            errors.append(f"{model} 的短評有 {length} 字，須為 250–300 字")
        if URL.search(body):
            errors.append(f"{model} 的短評含網址")
        if re.search(r"[#*`|]|\r|(?<!\n)\n(?!\n)|\n{3}", body):
            errors.append(f"{model} 的短評含 Markdown 符號或非段落換行")
    return errors


def main():
    from build_site import DATA_DIR, build_data

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    facts = commands.add_parser("facts", help="匯出公開統計")
    check = commands.add_parser("check", help="檢查短評稿")
    for command in (facts, check):
        command.add_argument("--data", type=Path, default=Path(DATA_DIR), help="資料目錄")
    facts.add_argument("--month", required=True, help="統計月份（YYYY-MM）")
    facts.add_argument("--as-of", required=True, help="資料日期（YYYY-MM-DD）")
    facts.add_argument("--out", type=Path, help="輸出檔案（預設印到 stdout）")
    args = parser.parse_args()
    if args.command == "facts" and not (iso_date(args.month + "-01") and iso_date(args.as_of)):
        facts.error("--month 與 --as-of 必須是有效的月份與日期")
    try:
        data = build_data(args.data)
    except (json.JSONDecodeError, UnicodeDecodeError):
        parser.error("短評稿必須是有效的 UTF-8 JSON")
    if args.command == "check":
        errors = validate(data["commentary"], (row["model"] for row in data["model_totals"]))
        if errors:
            print("\n".join(errors), file=sys.stderr)
        return int(bool(errors))

    payload = compile_facts(data, args.month, args.as_of)
    output = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(output, encoding="utf-8")
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
