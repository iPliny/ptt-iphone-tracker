import csv
import datetime as dt
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("local_watch", Path(__file__).resolve().parents[1] / ".github/local_crawler_watch.py")
watch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watch)
NOW = dt.datetime(2026, 11, 7, 12, tzinfo=dt.timezone.utc)


def runs(tmp_path, rows):
    path = tmp_path / "runs.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["run_at", "shop", "status", "rows", "error"])
        writer.writerows([list(row) + [0, "private error"] for row in rows])
    return path



import tempfile
import unittest

class LocalCrawlerWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def test_latest_ok_ignores_failures_order_and_other_shops(self):
        tmp_path = self.home
        path = runs(tmp_path, [
            ("2026-11-07T20:00:00+09:00", "イオシス", "ok"),
            ("2026-11-07T21:00:00+09:00", "イオシス", "fetch_error"),
            ("2026-11-06T20:00:00+09:00", "イオシス", "ok"),
            ("2026-11-07T21:00:00+09:00", "other", "ok"),
            ("2026-11-06T21:59:59+00:00", "モバステ", "ok"),
        ])
        latest = watch.latest_success(path, NOW)
        stale, body = watch.report(latest, NOW)
        assert stale == ["モバステ"]
        assert latest["イオシス"].hour == 20
        assert "private error" not in body

    def test_threshold_exact_and_one_second_over(self):
        latest = {"モバステ": NOW - dt.timedelta(hours=14),
                  "イオシス": NOW - dt.timedelta(hours=14, seconds=1)}
        assert watch.report(latest, NOW)[0] == ["イオシス"]

    def test_missing_empty_invalid_future_and_naive_all_alert(self):
        tmp_path = self.home
        assert watch.report(watch.latest_success(tmp_path / "missing", NOW), NOW)[0] == list(watch.SHOPS)
        path = runs(tmp_path, [(value, "イオシス", "ok") for value in
                              ("invalid", "2026-11-07T12:00:00", "2026-11-08T12:00:00+09:00")])
        assert watch.report(watch.latest_success(path, NOW), NOW)[0] == list(watch.SHOPS)
        assert watch.report(watch.latest_success(runs(tmp_path, []), NOW), NOW)[0] == list(watch.SHOPS)

    def test_issue_lifecycle(self):
        calls = []
        api = lambda *args: calls.append(args)
        watch.reconcile(["モバステ"], "stale", [], api)
        assert calls[0][:2] == ("issue", "create")
        assert watch.TITLE in calls[0]
        calls.clear()
        watch.reconcile(["イオシス"], "still stale", [{"number": 5}], api)
        assert [call[1] for call in calls] == ["edit", "comment"]
        calls.clear()
        watch.reconcile([], "recovered", [{"number": 5}], api)
        assert [call[1] for call in calls] == ["edit", "comment", "close"]
        calls.clear()
        watch.reconcile([], "healthy", [], api)
        assert calls == []

    def test_open_alerts_filters_title_prs_and_reads_all_pages(self):
        import json
        def api(*args):
            assert "--paginate" in args and "--slurp" in args
            return json.dumps([[{"number": 1, "title": watch.TITLE}, {"number": 2, "title": "other"}],
                               [{"number": 3, "title": watch.TITLE, "pull_request": {}},
                                {"number": 4, "title": watch.TITLE}]])
        assert watch.open_alerts(api) == [{"number": 1, "title": watch.TITLE}, {"number": 4, "title": watch.TITLE}]


    def test_runs_fixture_uses_production_columns_and_shop_names(self):
        path = Path(__file__).parent / "fixtures/jp/local-runs-watch.csv"
        with path.open() as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(reader.fieldnames, ["run_at", "shop", "status", "rows", "error"])
            self.assertEqual({row["shop"] for row in reader}, {"モバステ", "イオシス"})
        latest = watch.latest_success(path, NOW)
        self.assertEqual(watch.report(latest, NOW)[0], [])
        self.assertEqual(latest["イオシス"].hour, 9)

    def test_unchanged_stale_set_edits_body_without_comment(self):
        calls = []
        api = lambda *args: calls.append(args)
        watch.reconcile(["モバステ", "イオシス"], "first", [], api)
        body = calls[0][-1]
        for _ in range(3):
            calls.clear()
            watch.reconcile(["イオシス", "モバステ"], "updated", [{"number": 5, "body": body}], api)
            self.assertEqual([call[1] for call in calls], ["edit"])
            body = calls[0][-1]
        calls.clear()
        watch.reconcile(["イオシス"], "changed", [{"number": 5, "body": body}], api)
        self.assertEqual([call[1] for call in calls], ["edit", "comment"])
