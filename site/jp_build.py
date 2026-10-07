"""日本頁的獨立建置；僅標準函式庫、不讀取台灣資料、不改原始 CSV。"""
import csv
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


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
    payload = {name: read_rows(source / f"{name}.csv") for name in ("latest", "prices", "runs")}
    payload["generated_at"] = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(timespec="seconds")
    payload["downloads"] = []
    for name in ("latest", "prices", "runs"):
        path = source / f"{name}.csv"
        if path.exists():
            (out / "data" / "jp").mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out / "data" / "jp" / path.name)
            payload["downloads"].append(name)
    (out / "jp" / "data.json").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return payload
