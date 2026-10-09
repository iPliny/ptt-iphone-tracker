"""由真實 HTML fixture 製造示意歷史，僅供截圖。必須明確指定暫存資料根目錄。"""
import argparse
import copy
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from jp.buyback import (parse_mobilemix, parse_iosys, parse_amemoba, apply_results,
                        IOSYS_PAGES, AMEMOBA_PAGES, TOKYO)


def preview(data_root):
    data_root = Path(data_root).resolve()
    if data_root == ROOT / "data" or ROOT / "data" in data_root.parents:
        raise ValueError("示意資料不得寫入專案 data/；請使用 /tmp/ 下的空目錄")
    dest = data_root / "jp"
    if dest.exists():
        raise ValueError("請使用空目錄，避免混入舊示意資料")
    fixtures = ROOT / "tests/fixtures/jp"
    read = lambda name: (fixtures / f"{name}.html").read_text(encoding="utf-8")
    base = [dict(shop="mobile-mix", rows=parse_mobilemix(read("mobilemix"))[0])]
    for shop, names, parser, pages in [
        ("イオシス", ["iosys-pro", "iosys-max", None, None, "iosys-17"], parse_iosys, IOSYS_PAGES),
        ("アメモバ", ["amemoba-pro", "amemoba-max", "amemoba-17pro"], parse_amemoba, AMEMOBA_PAGES),
    ]:
        rows = [r for name, (url, model) in zip(names, pages.items()) if name
                for r in parser(read(name), url)[0] if r["model"] == model]
        base.append(dict(shop=shop, rows=rows))
    today = datetime.now(TOKYO).replace(hour=9, minute=30, second=0, microsecond=0)
    adjustments = [[-4000, -2000, 0], [-1000, -1000, 1000], [-1000, 0, 1000],
                   [1000, 2000, 0], [0, 1000, 2000], [-2000, 0, 1000], [0, 0, 0]]
    for day, offsets in enumerate(adjustments):
        results = copy.deepcopy(base)
        for index, result in enumerate(results):
            for row in result["rows"]:
                row["price_jpy"] += offsets[index]
        if day == 3:
            results[2]["rows"] = [r for r in results[2]["rows"] if not (r["model"] == "iPhone 18 Pro" and r["storage"] == "256GB")]
        apply_results(dest, results, (today - timedelta(days=6-day)).isoformat())
    return dest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, type=Path)
    print(preview(parser.parse_args().data))
