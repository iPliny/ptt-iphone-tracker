"""家用 IP 日本爬蟲：買取寫入 --data/local，販賣價寫入 --data/sell。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import buyback as jp
from .local_lock import execution_lock
from .local_pastec import PASTEC_INDEX, PASTEC_SHOP, discover_pastec_pages, parse_pastec
from .local_iosys import (IOSYS_SELL_INDEX, SELL_CONDITIONS, discover_iosys_pages,
                          iosys_next_page, minimum_prices, parse_iosys_sell)

HOST_INTERVALS = {"pastec.net": 10, "www.suruga-ya.jp": 30,
                  "suruga-ya.jp": 30, "iosys.co.jp": 10}
SOURCES = ("pastec", "iosys-sell", "iosys-buyback")
MAX_PAGES = 100  # 版型異常／循環分頁時整店失敗，不寫不完整快照。


def fetch(url):
    return jp.fetch(url, host_intervals=HOST_INTERVALS)


def collect(only=SOURCES, fetcher=None):
    fetcher = fetcher or fetch
    results = []
    for source in only:
        if source == "iosys-buyback":
            results.extend(dict(r, source=source) for r in jp.collect(fetcher, only=("イオシス",)))
            continue
        shop = PASTEC_SHOP if source == "pastec" else "イオシス"
        result = dict(source=source, shop=shop, rows=[], status="ok", error="", shop_updated="")
        dates, seen = [], set()
        phase = "fetch_error"
        try:
            index = fetcher(PASTEC_INDEX if source == "pastec" else IOSYS_SELL_INDEX)
            phase = "parse_error"
            pages = discover_pastec_pages(index) if source == "pastec" else discover_iosys_pages(index)
            for first, expected in pages.items():
                url = first
                while url:
                    if url in seen or len(seen) >= MAX_PAGES:
                        raise jp.ParseError("規格或分頁重複，或超過本機爬蟲頁數上限")
                    seen.add(url)
                    phase = "fetch_error"
                    html = fetcher(url)
                    phase = "parse_error"
                    parsed, updated = (parse_pastec(html, url) if source == "pastec"
                                       else parse_iosys_sell(html, url))
                    if source == "pastec":
                        if any((r["model"], r["storage"]) != expected for r in parsed):
                            raise jp.ParseError("モバステ規格頁與列表不一致")
                    else:
                        parsed = [r for r in parsed if r["model"] in expected]
                    if not parsed:
                        raise jp.ParseError("規格頁解析 0 筆")
                    result["rows"].extend(parsed)
                    if updated:
                        dates.append(updated)
                    url = iosys_next_page(html, url) if source == "iosys-sell" else None
            if source == "iosys-sell":
                result["rows"] = minimum_prices(result["rows"])
            result["shop_updated"] = max(dates, default="")
        except Exception as exc:
            # 不把遠端 HTML、網址 query 或例外全文寫入 log／CSV。
            result["status"] = phase
            result["error"] = str(exc) if isinstance(exc, jp.ParseError) else jp.fetch_error(exc)
        results.append(result)
    return results


def save_or_check(data_dir, results, *, dry_run=False, run_at=None):
    reports = []
    for result in results:
        selling = result["source"] == "iosys-sell"
        target = Path(data_dir) / "sell" if selling else Path(data_dir) / "local"
        conditions = SELL_CONDITIONS if selling else ("未開封", "中古上限")
        status = result["status"]
        if status == "ok":
            previous = {jp.row_key(r): r for r in jp.read_csv(target / "latest.csv")
                        if r["shop"] == result["shop"]}
            if not selling and not previous:
                # 第一次搬到獨立檔案時仍沿用舊快照做筆數防呆。
                previous = {jp.row_key(r): r for r in jp.read_csv(Path(data_dir) / "latest.csv")
                            if r["shop"] == result["shop"]}
            try:
                jp.validate_rows(result["shop"], result["rows"], previous, conditions=conditions)
            except jp.ParseError as exc:
                status = "parse_error"
                result = dict(result, status=status, error=str(exc))
        if not dry_run:
            reports.extend(jp.apply_results(target, [result], run_at, conditions=conditions,
                                            baseline_dir=None if selling else data_dir))
            continue
        reports.append(dict(shop=result["shop"], status=status, rows=len(result["rows"]),
                            error=result.get("error", "")))
    return reports


def source_list(value):
    sources = value.split(",")
    if not sources or any(s not in SOURCES for s in sources) or len(set(sources)) != len(sources):
        raise argparse.ArgumentTypeError("--only 只接受 pastec、iosys-sell、iosys-buyback，以逗號分隔且不可重複")
    return tuple(sources)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="私人資料 repo 的 jp 目錄")
    parser.add_argument("--dry-run", action="store_true", help="解析與驗證，但不建立或修改檔案")
    parser.add_argument("--only", type=source_list, default=SOURCES, help="pastec,iosys-sell,iosys-buyback（預設全部）")
    args = parser.parse_args(argv)
    try:
        with execution_lock():
            results = collect(args.only)
            report = save_or_check(args.data, results, dry_run=args.dry_run)
    except (OSError, RuntimeError):
        report = [dict(shop="本機爬蟲", status="local_error", rows=0)]
    print(json.dumps([{**{k: r[k] for k in ("shop", "status", "rows")},
                       **({"error": jp.fetch_error(RuntimeError(r.get("error", "")))} if r["status"] == "fetch_error" else {})}
                      for r in report],
                     ensure_ascii=False, indent=2))
    return 0 if all(r["status"] == "ok" for r in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
