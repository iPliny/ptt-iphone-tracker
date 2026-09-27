"""網站建置腳本的離線測試。執行：python -m unittest"""
import csv
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "site"))
import build_site as S  # noqa: E402

LISTING_HEADER = ["source_url", "post_time", "title", "status", "sold_detected_at", "days_to_sell",
                  "model", "storage", "全新未拆封機", "battery_health", "price", "first_price",
                  "warranty", "notes", "model_raw", "first_seen", "last_checked", "body_hash"]


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def listing(url, post, status="在售", price="10000", sold_at="", days="", model="iPhone 15", storage="128GB"):
    return {"source_url": url, "post_time": post, "status": status, "sold_detected_at": sold_at,
            "days_to_sell": days, "model": model, "storage": storage, "全新未拆封機": "否",
            "price": price, "first_price": price, "last_checked": "2026-09-03 12:00:00"}


class BuildSiteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        write_csv(os.path.join(self.dir, "listings.csv"), LISTING_HEADER, [
            listing("u1", "2026-09-01 10:00:00", status="已售出", price="20000",
                    sold_at="2026-09-02 09:00:00", days="0.9"),
            listing("u2", "2026-09-01 11:00:00", status="已刪除"),
            listing("u3", "2026-09-03 08:00:00", price="12000"),
            listing("u4", "2026-09-03 09:00:00", status="略過", model=""),
        ])
        write_csv(os.path.join(self.dir, "events.csv"), S_EVENT_HEADER, [
            {"time": "2026-09-02 09:00:00", "source_url": "u1", "event": "狀態變更", "detail": "在售 → 已售出"},
            {"time": "2026-09-03 07:00:00", "source_url": "u2", "event": "狀態變更", "detail": "在售 → 已刪除"},
            {"time": "2026-09-03 08:30:00", "source_url": "u3", "event": "價格變動", "detail": "13000 → 12000"},
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_daily_series(self):
        data = S.build_data(self.dir, now=datetime(2026, 9, 3, 12))
        days = {d["date"]: d for d in data["days"]}
        self.assertEqual(sorted(days), ["2026-09-01", "2026-09-02", "2026-09-03"])  # 中間沒動靜的日子也要補
        self.assertEqual((days["2026-09-01"]["new"], days["2026-09-01"]["on_shelf"]), (2, 2))
        self.assertEqual((days["2026-09-02"]["sold"], days["2026-09-02"]["on_shelf"]), (1, 1))
        d3 = days["2026-09-03"]
        self.assertEqual((d3["new"], d3["deleted"], d3["price_changes"], d3["on_shelf"]), (1, 1, 1, 1))

    def test_skipped_rows_excluded(self):
        data = S.build_data(self.dir)
        self.assertEqual(data["counts"]["total"], 3)
        self.assertNotIn("u4", [r["url"] for r in data["listings"]])
        self.assertEqual(data["counts"]["已售出"], 1)

    def test_model_stats(self):
        (m,) = S.build_data(self.dir)["models"]
        self.assertEqual((m["listed"], m["active"], m["sold"]), (3, 1, 1))
        self.assertEqual((m["median_price"], m["median_sold_price"], m["median_days"]), (12000, 20000, 0.9))

    def test_missing_events_file(self):
        os.remove(os.path.join(self.dir, "events.csv"))
        data = S.build_data(self.dir)
        self.assertEqual(data["events"], [])
        self.assertEqual(sum(d["deleted"] for d in data["days"]), 0)  # 沒有事件就不知道刪文日

    def test_build_writes_site(self):
        out = os.path.join(self.dir, "out")
        S.build(out, self.dir)
        for name in S.STATIC_FILES + ["data.json", "data/listings.csv"]:
            self.assertTrue(os.path.exists(os.path.join(out, name)), name)
        with open(os.path.join(out, "data.json"), encoding="utf-8") as f:
            self.assertIn("days", json.load(f))

    def test_real_data_builds(self):
        """repo 內現有的 data/ 也要能建置成功。"""
        data = S.build_data()
        self.assertGreater(data["counts"]["total"], 0)


S_EVENT_HEADER = ["time", "source_url", "event", "detail"]

if __name__ == "__main__":
    unittest.main()
