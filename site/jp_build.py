"""日本頁的獨立建置；僅標準函式庫、不讀取台灣資料、不改原始 CSV。"""
import csv
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jp_pages import CONDITIONS, MODELS, SHOPS, STORAGES

PRICE_FIELDS = ("shop", "model", "storage", "condition", "carrier", "color", "price_jpy", "observed_at", "source_url")
LATEST_FIELDS = PRICE_FIELDS + ("since", "last_checked", "shop_updated")


def public_rows(rows, fields):
    """只輸出介面會顯示的 SIMフリー機型與明列欄位；新增 CSV 欄位不會自動公開。"""
    return [{k: row.get(k, "") for k in fields} for row in rows
            if row.get("carrier") == "SIMフリー" and row.get("condition") in CONDITIONS
            and row.get("model") in MODELS and row.get("shop") in SHOPS
            and row.get("storage") in STORAGES]


def public_runs(rows):
    """快報只需最近七天的成功時間；狀態卡另外保留各店最後一次及最後成功。"""
    valid = []
    for row in rows:
        try:
            at = datetime.fromisoformat(row["run_at"])
            if at.tzinfo is None or row.get("shop") not in SHOPS:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        valid.append((at, row))
    if not valid:
        return []
    valid.sort(key=lambda pair: pair[0])
    cutoff = valid[-1][0] - timedelta(days=7)
    selected = {i for i, (at, r) in enumerate(valid) if at >= cutoff and r.get("status") == "ok"}
    for shop in SHOPS:
        for successful in (False, True):
            matches = [i for i, (_, r) in enumerate(valid) if r.get("shop") == shop
                       and (not successful or r.get("status") == "ok")]
            if matches:
                selected.add(matches[-1])
    return [{k: valid[i][1].get(k, "") for k in ("shop", "run_at", "status")} for i in sorted(selected)]


def read_rows(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        if "price_jpy" in row:
            try:
                row["price_jpy"] = int(row["price_jpy"])
            except (ValueError, TypeError):
                row["price_jpy"] = None
    return rows


def build_jp(out_dir, data_dir):
    out, source = Path(out_dir), Path(data_dir) / "jp"
    shutil.copytree(Path(__file__).parent / "jp", out / "jp", dirs_exist_ok=True)
    payload = {
        "latest": public_rows(read_rows(source / "latest.csv"), LATEST_FIELDS),
        "prices": public_rows(read_rows(source / "prices.csv"), PRICE_FIELDS),
        "runs": public_runs(read_rows(source / "runs.csv")),
    }
    payload["generated_at"] = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds")
    (out / "jp" / "data.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return payload
