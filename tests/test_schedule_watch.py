"""排程看門狗（.github/schedule_watch.py）的時間點計算與判斷。"""
import datetime as dt
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("schedule_watch", ROOT / ".github" / "schedule_watch.py")
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)

UTC = dt.timezone.utc


def t(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


class ScheduleWatchTest(unittest.TestCase):
    def test_reads_crons_from_workflows(self):
        self.assertEqual(sw.crons_of("track.yml"), ["0 0,6,12,18 * * *"])
        self.assertEqual(sw.crons_of("column.yml"), ["0 12 * * 0"])
        for wf in sw.WATCHED:
            self.assertTrue(sw.crons_of(wf), wf)

    def test_last_slot(self):
        track = ["0 0,6,12,18 * * *"]
        self.assertEqual(sw.last_slot(track, t("2026-10-25T10:15:34")), t("2026-10-25T06:00"))
        self.assertEqual(sw.last_slot(track, t("2026-10-25T12:00")), t("2026-10-25T12:00"))
        self.assertEqual(sw.last_slot(["17 0,6,12 * * *"], t("2026-10-25T00:10")), t("2026-10-24T12:17"))

    def test_weekly_slot_is_sunday(self):
        column = ["0 12 * * 0"]
        # 2026-10-25 是週日
        self.assertEqual(sw.last_slot(column, t("2026-10-25T12:18")), t("2026-10-25T12:00"))
        self.assertEqual(sw.last_slot(column, t("2026-10-25T11:59")), t("2026-10-18T12:00"))
        self.assertEqual(sw.last_slot(["0 12 * * 7"], t("2026-10-25T12:18")), t("2026-10-25T12:00"))

    def test_cron_fields(self):
        self.assertEqual(sw.parse_field("7,22,37,52", 0, 59), {7, 22, 37, 52})
        self.assertEqual(sw.parse_field("*/20", 0, 59), {0, 20, 40})
        self.assertEqual(sw.parse_field("1-3", 0, 6), {1, 2, 3})

    def test_needs_dispatch(self):
        slot = t("2026-10-25T12:00")
        self.assertFalse(sw.needs_dispatch(slot, [], t("2026-10-25T12:03")))  # 還在寬限內
        self.assertTrue(sw.needs_dispatch(slot, [], t("2026-10-25T12:07")))
        self.assertFalse(sw.needs_dispatch(slot, [{"id": 1}], t("2026-10-25T15:00")))

    def test_gate_skips_late_schedule_only_when_slot_already_ran(self):
        slot = t("2026-10-25T06:00")
        self.assertTrue(sw.should_run(slot, [{"run_number": 5}], "5"))  # 只有自己
        self.assertFalse(sw.should_run(slot, [{"run_number": 4}, {"run_number": 5}], "5"))

    def test_gate_ignores_later_pending_and_cancelled_runs(self):
        slot = t("2026-10-25T06:00")
        # 4 正在跑、5 在 concurrency 排隊：4 不因 5 略過，5 輪到時因 4 略過
        runs = [{"run_number": 4, "conclusion": None}, {"run_number": 5, "conclusion": None}]
        self.assertTrue(sw.should_run(slot, runs, "4"))
        self.assertFalse(sw.should_run(slot, runs, "5"))
        self.assertTrue(sw.should_run(slot, [{"run_number": 4, "conclusion": "cancelled"}], "5"))
        self.assertTrue(sw.needs_dispatch(slot, [{"run_number": 4, "conclusion": "cancelled"}], t("2026-10-25T07:00")))


if __name__ == "__main__":
    unittest.main()
