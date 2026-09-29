"""改價時間的離線回歸：編輯時間快照與後續純編輯必須分開。"""
import sys
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import tracker as T

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
import build_site as S


URL = "https://www.ptt.cc/bbs/MacShop/M.1790568211.A.DCF.html"


class PriceTimeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.events = Path(self.tmp.name) / "events.csv"
        self.times = Path(self.tmp.name) / "price_event_times.csv"
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(T, "EVENTS_FILE", str(self.events)))
        self.stack.enter_context(patch.object(T, "EXTRACTOR", "rules"))
        self.stack.enter_context(patch.object(T, "REPARSE", False))
        self.rows = {}
        self.stats = dict.fromkeys(("new", "sold", "deleted", "price_changes", "errors"), 0)

    def visit(self, at, price=11000, edits=(), note="", pushes="", parse_price=True):
        # 使用使用者提供的實際編輯列，本文僅保留測試所需的型號、容量、售價。
        html = ('<div id="main-content"><div class="article-metaline">'
                '<span class="article-meta-tag">標題</span>'
                '<span class="article-meta-value">[販售] iPhone 13 Pro Max 256GB</span></div>'
                f'[型號] iPhone 13 Pro Max\n[規格] 256GB\n[售價] {price}\n'
                f'[商品照/補充說明] {note}\n--\n※ 發信站: 批踢踢實業坊(ptt.cc)\n' +
                ''.join(f'※ 編輯: celia6238 (1.160.249.21 臺灣), {e}\n' for e in edits) + pushes + '</div>')
        observed = datetime.fromisoformat(at + "+08:00")
        legacy = observed.astimezone(T.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        with patch.object(T, "fetch", return_value=(200, html)), \
                patch.object(T, "taipei_now", return_value=observed), \
                patch.object(T, "now_str", return_value=legacy):
            T.process_article(URL, self.rows, parse_price, self.stats)

    def records(self, path):
        return S.read_csv(str(path))

    def test_price_edit_detail_edit_then_second_price_edit(self):
        self.visit("2026-09-29T07:00:00")
        self.visit("2026-09-29T10:59:34", 10000, ["09/29/2026 08:53:46"])
        first_event_bytes = self.events.read_bytes()
        first_time_bytes = self.times.read_bytes()
        first = self.records(self.times)[0]
        self.assertEqual((first["time"], first["occurred_at"], first["detected_at"], first["time_basis"]),
                         ("2026-09-29 02:59:34", "2026-09-29T08:53:46+08:00",
                          "2026-09-29T10:59:34+08:00", "ptt_edit"))
        self.visit("2026-09-29T12:00:00", 10000, ["09/29/2026 11:20:00"], note="補充面交地點")
        self.assertEqual(self.events.read_bytes(), first_event_bytes)
        self.assertEqual(self.times.read_bytes(), first_time_bytes)
        self.assertEqual(self.rows[URL]["last_edit_at"], "2026-09-29T11:20:00+08:00")
        self.assertEqual(self.rows[URL]["status"], T.STATUS_ACTIVE)
        self.visit("2026-09-29T15:00:00", 9500, ["09/29/2026 14:30:00"], note="補充面交地點")
        snapshots = self.records(self.times)
        self.assertEqual(len(snapshots), 2)
        self.assertEqual(snapshots[0], first)
        self.assertEqual(snapshots[1]["occurred_at"], "2026-09-29T14:30:00+08:00")
        self.assertEqual(self.stats["price_changes"], 2)
        self.assertTrue(self.events.read_bytes().startswith(first_event_bytes))
        self.assertTrue(self.times.read_bytes().startswith(first_time_bytes))

    def test_edit_record_only_does_not_extract_or_create_price_event(self):
        self.visit("2026-09-29T07:00:00")
        before = self.events.read_bytes()
        with patch.object(T, "safe_extract", side_effect=AssertionError("編輯紀錄不屬於本文")):
            self.visit("2026-09-29T09:00:00", edits=["09/29/2026 08:53:46"])
        self.assertEqual(self.events.read_bytes(), before)
        self.assertFalse(self.times.exists())
        self.assertEqual(self.rows[URL]["last_edit_at"], "2026-09-29T08:53:46+08:00")

    def test_first_seen_with_edits_does_not_invent_price_change(self):
        self.visit("2026-09-29T09:00:00", 10000, ["09/29/2026 08:53:46"])
        self.assertEqual([e["event"] for e in self.records(self.events)], ["新刊登"])
        self.assertFalse(self.times.exists())

    def test_latest_edit_at_detection_is_selected(self):
        self.visit("2026-09-29T07:00:00")
        self.visit("2026-09-29T09:00:00", 10000,
                   ["09/29/2026 07:30:00", "09/29/2026 08:53:46"])
        self.assertEqual(self.records(self.times)[0]["occurred_at"], "2026-09-29T08:53:46+08:00")

    def test_invalid_or_missing_latest_edit_falls_back_to_detection(self):
        for edits in ([], ["09/29/2026 10:00:00"], ["09/29/2026 06:00:00"],
                      ["09/29/2026 07:00:00"], ["09/27/2026 01:00:00"],
                      ["09/29/2026 08:00:00", "09/99/2026 08:53:46"]):
            with self.subTest(edits=edits):
                self.rows = {}
                self.visit("2026-09-29T07:00:00")
                self.visit("2026-09-29T09:00:00", 10000, edits)
                saved = self.records(self.times)[-1]
                self.assertEqual(saved["time_basis"], "detected")
                self.assertEqual(saved["occurred_at"], "2026-09-29T09:00:00+08:00")

    def test_old_listing_without_aware_check_time_accepts_current_edit(self):
        self.visit("2026-09-29T07:00:00")
        del self.rows[URL]["price_checked_at"]
        self.visit("2026-09-29T09:00:00", 10000, ["09/29/2026 08:53:46"])
        self.assertEqual(self.records(self.times)[0]["time_basis"], "ptt_edit")

    def test_failed_extraction_retries_without_losing_price_interval(self):
        self.visit("2026-09-29T07:00:00")
        before = dict(self.rows[URL])
        with patch.object(T, "safe_extract", return_value=None):
            self.visit("2026-09-29T09:00:00", 10000, ["09/29/2026 08:53:46"])
        for field in ("price", "body_hash", "price_checked_at"):
            self.assertEqual(self.rows[URL][field], before[field])
        self.assertFalse(self.times.exists())
        self.visit("2026-09-29T11:00:00", 10000, ["09/29/2026 08:53:46"])
        self.assertEqual(self.records(self.times)[0]["occurred_at"], "2026-09-29T08:53:46+08:00")

    def test_reparse_correction_is_not_price_change(self):
        self.visit("2026-09-29T07:00:00")
        self.rows[URL]["price"] = 12000
        with patch.object(T, "REPARSE", True):
            self.visit("2026-09-29T09:00:00", edits=["09/29/2026 08:53:46"])
        self.assertFalse(self.times.exists())
        self.assertEqual(self.records(self.events)[-1]["event"], "重新解析修正")

    def test_status_only_visit_does_not_consume_unparsed_price_change(self):
        self.visit("2026-09-29T07:00:00")
        before = dict(self.rows[URL])
        self.visit("2026-09-29T09:00:00", 10000, ["09/29/2026 08:53:46"], parse_price=False)
        for field in ("price", "body_hash", "price_checked_at"):
            self.assertEqual(self.rows[URL][field], before[field])
        self.assertFalse(self.times.exists())
        self.visit("2026-09-29T11:00:00", 10000, ["09/29/2026 08:53:46"])
        self.assertEqual(self.records(self.times)[0]["occurred_at"], "2026-09-29T08:53:46+08:00")

    def test_push_only_keeps_price_history(self):
        self.visit("2026-09-29T07:00:00")
        before = self.events.read_bytes()
        with patch.object(T, "safe_extract", side_effect=AssertionError("推文不應觸發萃取")):
            self.visit("2026-09-29T09:00:00", pushes='<div class="push">私</div>')
        self.assertEqual(self.events.read_bytes(), before)
        self.assertFalse(self.times.exists())

    def test_build_groups_sorts_and_counts_by_frozen_edit_time(self):
        self.visit("2026-09-28T22:00:00")
        self.visit("2026-09-29T10:00:00", 10000, ["09/28/2026 23:53:46"])
        self.visit("2026-09-29T12:00:00", 9500, ["09/29/2026 11:00:00"])
        # 再次編輯只有補充說明，網站不得把兩笔舊事件都搬到最後編輯時間。
        self.visit("2026-09-30T09:00:00", 9500, ["09/30/2026 08:00:00"], note="補照片")
        T.save_listings(self.rows, str(Path(self.tmp.name) / "listings.csv"))
        data = S.build(str(Path(self.tmp.name) / "site"), self.tmp.name)
        prices = [e for e in data["events"] if e["event"] == "價格變動"]
        self.assertEqual([e["time"] for e in prices], ["2026-09-29 11:00:00", "2026-09-28 23:53:46"])
        days = {d["date"]: d["price_changes"] for d in data["days"]}
        self.assertEqual((days["2026-09-28"], days["2026-09-29"]), (1, 1))
        self.assertEqual(data["listings"][0]["last_edit_at"], "2026-09-30T08:00:00+08:00")
        self.assertTrue((Path(self.tmp.name) / "site/data/price_event_times.csv").exists())

    def test_legacy_events_keep_detection_time_and_are_not_modified(self):
        self.visit("2026-09-29T07:00:00")
        self.visit("2026-09-29T09:00:00", 10000, ["09/29/2026 08:53:46"])
        events = self.records(self.events)
        before = [dict(e) for e in events]
        result = S.attach_price_times(events, [])
        self.assertEqual(events, before)
        self.assertEqual(result[-1]["time"], events[-1]["time"])
        self.assertEqual(result[-1]["time_basis"], "detected")

    def test_site_rejects_bad_snapshot_and_normalizes_explicit_timezone(self):
        original = {"time": "2026-09-29 02:59:34", "source_url": URL,
                    "event": "價格變動", "detail": "11000 → 10000"}
        saved = dict(original, occurred_at="2026-09-29T00:53:46Z",
                     detected_at="2026-09-29T02:59:34Z", time_basis="ptt_edit")
        result = S.attach_price_times([original], [saved])[0]
        self.assertEqual(result["time"], "2026-09-29 08:53:46")
        for bad in ("bad", "2026-09-29T08:00:00", "2026-09-30T00:00:00Z"):
            result = S.attach_price_times([original], [dict(saved, occurred_at=bad)])[0]
            self.assertEqual(result["time"], original["time"])
            self.assertEqual(result["time_basis"], "detected")

    def test_aware_clock_and_legacy_time_are_distinct(self):
        self.assertEqual(T.taipei_now().utcoffset(), T.timedelta(hours=8))
        self.assertIsNone(T.parse_aware_time("2026-09-29 02:59:34"))
        self.assertEqual(T.parse_aware_time("2026-09-29T00:53:46Z").hour, 8)


if __name__ == "__main__":
    unittest.main()
