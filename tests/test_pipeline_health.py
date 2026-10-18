"""排程健康檢查與持久重試的離線驗收；所有抓取、Claude 呼叫皆使用替身。"""
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import anthropic
import httpx2
import tracker as T
from tests import test_tracker as fixtures


class PipelineHealthTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PipelineTest(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.tmp = Path(self.fixture.tmp.name)
        self.env = patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "RUNNER_TEMP": str(self.tmp),
                                         "GITHUB_STEP_SUMMARY": str(self.tmp / "summary.md")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(setattr, sys, "argv", sys.argv[:])
        extractor = patch.object(T, "EXTRACTOR", "rules")
        extractor.start()
        self.addCleanup(extractor.stop)
        self.health = self.tmp / "track-health.txt"

    def run_tracker(self, *args):
        return self.fixture.run_main("--extractor", "rules", *args)

    def freeform(self):
        path = self.fixture.paths[0]
        title, body = fixtures.ClaudeFallbackTest.FREEFORM
        self.fixture.arts[path] = (title.replace("17 Pro", "iPhone 17 Pro"), body, "")
        self.fixture.listed = {path}
        return T.BASE_URL + path

    @staticmethod
    def api_error(kind, message):
        code = {anthropic.AuthenticationError: 401, anthropic.PermissionDeniedError: 403,
                anthropic.BadRequestError: 400, anthropic.InternalServerError: 529}[kind]
        response = httpx2.Response(code, request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
        return kind(message, response=response, body={"message": message})

    def test_board_first_page_failure_and_empty_queue(self):
        with patch.object(T, "fetch", return_value=(None, None)):
            self.run_tracker()
        self.assertIn("看板第一頁抓取失敗", self.health.read_text())
        self.assertTrue(self.health.read_text().startswith("FAILED\n"))
        self.assertIn("看板第一頁", (self.tmp / "summary.md").read_text())

    def test_empty_successful_board_is_healthy(self):
        self.fixture.listed = set()
        self.run_tracker()
        self.assertTrue(self.health.read_text().startswith("OK\n"))

    def test_later_board_page_failure_does_not_fail_first_page_check(self):
        original = self.fixture.fake_fetch
        with patch.object(T, "fetch", side_effect=lambda url: (None, None) if "index1" in url else original(url)):
            self.run_tracker()
        self.assertTrue(self.health.read_text().startswith("OK\n"))

    def test_all_articles_fail_but_404_counts_as_success(self):
        original = self.fixture.fake_fetch
        with patch.object(T, "fetch", side_effect=lambda url: original(url) if "index" in url else (503, "")):
            self.run_tracker()
        self.assertIn("沒有任何一篇成功取得 200 或 404", self.health.read_text())
        with patch.object(T, "fetch", side_effect=lambda url: original(url) if "index" in url else (404, "")):
            self.run_tracker()
        self.assertTrue(self.health.read_text().startswith("OK\n"))

    def test_account_errors_fail_but_timeout_overload_and_other_400_do_not(self):
        self.freeform()
        for error, failed in [
            (self.api_error(anthropic.AuthenticationError, "invalid api key"), True),
            (self.api_error(anthropic.PermissionDeniedError, "permission denied"), True),
            (self.api_error(anthropic.BadRequestError, "Your credit balance is too low"), True),
            (TimeoutError("timeout"), False),
            (self.api_error(anthropic.InternalServerError, "overloaded"), False),
            (self.api_error(anthropic.BadRequestError, "invalid schema"), False),
        ]:
            with self.subTest(error=error), patch.object(T, "claude_extract", side_effect=error):
                self.run_tracker("--extractor", "claude")
                self.assertEqual(self.health.read_text().startswith("FAILED\n"), failed)

    def test_general_error_threshold_is_strictly_greater_than_ten(self):
        self.assertEqual(T.health_failures({"errors": 10, "fetched": 1}, 1), [])
        self.assertIn("超過門檻 10", T.health_failures({"errors": 11, "fetched": 1}, 1)[0])

    def test_retry_survives_missing_board_then_success_removes_it(self):
        url = self.freeform()
        with patch.object(T, "claude_extract", side_effect=TimeoutError("timeout")):
            self.run_tracker("--extractor", "claude")
        retry = T.load_extract_retries()[url]
        self.assertEqual((retry["attempts"], retry["last_error"]), ("1", "timeout"))
        self.assertNotIn(url, T.load_listings())
        self.fixture.listed = set()  # 下輪看板已掃不到，仍須獨立重試。
        with patch.object(T, "claude_extract", side_effect=TimeoutError("again")):
            self.run_tracker("--extractor", "claude")
        retry2 = T.load_extract_retries()[url]
        self.assertEqual(retry2["attempts"], "2")
        self.assertEqual(retry2["first_failed"], retry["first_failed"])
        with patch.object(T, "claude_extract", return_value=fixtures.ClaudeFallbackTest.CLAUDE_OUT):
            rows = self.run_tracker("--extractor", "claude")
        self.assertEqual(rows[url]["extractor"], "claude")
        self.assertEqual(rows[url]["first_seen"], retry["first_failed"])
        self.assertEqual(T.load_extract_retries(), {})

    def seed_retry(self, url, age=0):
        first = (T.datetime.now() - timedelta(days=age)).strftime("%Y-%m-%d %H:%M:%S")
        T.save_extract_retries({url: {"source_url": url, "first_failed": first, "last_failed": first,
                                     "attempts": 1, "last_error": "timeout"}})

    def test_retry_expires_at_fourteen_days_without_fetching_or_calling_claude(self):
        url = self.freeform()
        self.fixture.listed = set()
        self.seed_retry(url, T.RETRY_DAYS)
        with patch.object(T, "claude_extract") as claude:
            rows = self.run_tracker("--extractor", "claude")
        claude.assert_not_called()
        self.assertEqual(rows[url]["status"], "略過")
        self.assertEqual(T.load_extract_retries(), {})
        self.assertEqual(self.run_tracker()[url]["status"], "略過")

    def test_retry_retained_before_fourteen_days(self):
        url = self.freeform()
        self.seed_retry(url, T.RETRY_DAYS - 1)
        with patch.object(T, "claude_extract", side_effect=TimeoutError("timeout")):
            self.run_tracker("--extractor", "claude")
        self.assertIn(url, T.load_extract_retries())
        self.assertNotIn(url, T.load_listings())

    def test_retry_removed_after_404_skip_or_multi(self):
        url = self.freeform()
        path = self.fixture.paths[0]
        for result in ("404", "skip", "multi"):
            with self.subTest(result=result):
                T.save_listings({})
                self.seed_retry(url)
                if result == "404":
                    self.fixture.arts[path] = None
                    self.fixture.listed = set()
                elif result == "multi":
                    self.fixture.arts[path] = (
                        "[販售] 高屏 iPhone 17 pro銀512g/16 綠 512g",
                        "[型號]\n1. iPhone 17 Pro\n2. iPhone 16\n[規格]\n1. 銀色，512g\n2. 湖水綠色，512g\n"
                        "[售價]\n1. 36000\n2. 16000\n", "")
                else:
                    self.fixture.arts[path] = (*fixtures.ClaudeFallbackTest.FREEFORM, "")
                with patch.object(T, "claude_extract", return_value={}):
                    rows = self.run_tracker("--extractor", "claude")
                self.assertEqual(T.load_extract_retries(), {})
                if result != "404":
                    self.assertEqual(rows[url]["status"], "略過")
                if result == "multi":
                    self.assertEqual(len(T.load_multi()[url]), 2)

    def test_health_report_written_after_all_data_and_summary(self):
        original = T.write_health_report
        def verify(stats, queue_size):
            for file in (T.LISTINGS_FILE, T.MULTI_FILE, T.RETRY_FILE, T.SUMMARY_FILE):
                self.assertTrue(Path(file).is_file(), file)
            self.assertTrue(T.load_listings())
            original(stats, queue_size)
        with patch.object(T, "write_health_report", side_effect=verify) as report:
            self.run_tracker()
        report.assert_called_once()

    def test_local_run_does_not_write_actions_result(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "false"}), \
                patch.object(T, "fetch", return_value=(None, None)):
            self.run_tracker()
        self.assertFalse(self.health.exists())

    def test_report_and_migrate_do_not_write_health_or_retry(self):
        for args in (("--report-only",), ("--migrate", str(self.tmp / "old.csv"))):
            (self.tmp / "old.csv").write_text("source_url\n")
            with patch.object(T, "fetch") as fetch:
                self.run_tracker(*args)
            fetch.assert_not_called()
            self.assertFalse(self.health.exists())
            self.assertFalse(Path(T.RETRY_FILE).exists())
