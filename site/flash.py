"""主站快訊的既有 48 小時規則；只輸出白名單欄位，不公開原始資料。"""
import math
import re
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP


def stamp(value):
    try:
        if not re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", value):
            return None
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def positive(value):
    try:
        return bool(str(value).strip()) and math.isfinite(float(value)) and float(value) > 0
    except (ValueError, TypeError):
        return False


def money(value):
    return f"{float(value):,.0f}"


def public_flash(events, listings, generated_at=None):
    times = [stamp(e.get("time", "")) for e in events]
    latest = max((t for t in times if t), default=None)
    corrected = {e.get("source_url") for e in events if e.get("event") == "重新解析修正"}
    by_url = {r.get("source_url"): r for r in listings}
    seen, items = set(), []
    for e in sorted(events, key=lambda e: e.get("time", ""), reverse=True):
        when, url = stamp(e.get("time", "")), e.get("source_url", "")
        r = by_url.get(url)
        if not when or not latest or (latest - when).total_seconds() > 48 * 3600 or not r or url in corrected or url in seen:
            continue
        if not re.match(r"^iPhone 1[678](?:\b|e\b)", r.get("model", "")) or not url.startswith("https://www.ptt.cc/bbs/MacShop/"):
            continue
        name = " ".join(v for v in [r.get("model"), r.get("storage"), "全新" if r.get("全新未拆封機") == "是" else ""] if v)
        text, kind = None, None
        if e.get("event") == "狀態變更" and e.get("detail", "").strip().endswith("已售出") and r.get("status") == "已售出" and positive(r.get("price")):
            kind, text = "sold", f"售出｜{name} 標價 NT${money(r['price'])}"
            days = r.get("days_to_sell", "").strip()
            try:
                if days and math.isfinite(float(days)) and float(days) >= 0:
                    rounded = Decimal.from_float(float(days)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                    text += f"，刊登 {rounded:.1f} 天賣掉"
            except (ValueError, TypeError):
                pass
        elif e.get("event") == "價格變動" and r.get("status") == "在售":
            prices = re.fullmatch(r"\s*([\d,]+)\s*→\s*([\d,]+)\s*", e.get("detail", ""))
            if not prices:
                continue
            try:
                old, now = [float(v.replace(",", "")) for v in prices.groups()]
            except ValueError:
                continue
            drop = old - now
            if old <= 0 or now <= 0 or drop <= 0 or drop / old > .3 or (drop < 500 and drop / old < .02):
                continue
            kind, text = "drop", f"降價｜{name} NT${money(old)} → NT${money(now)}"
        if text:
            seen.add(url)
            items.append(dict(kind=kind, time=e["time"], text=text, url=url))
            if len(items) == 6:
                break
    return {"schema_version": 1, "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(),
            "observed_through": latest.strftime("%Y-%m-%d %H:%M:%S") if latest else None, "items": items}
