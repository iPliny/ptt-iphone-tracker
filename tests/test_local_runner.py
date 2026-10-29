"""本機同步的離線測試；Git、爬取與 HOME 均使用暫存替身。"""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

from jp.local_lock import LOCK_ENV, execution_lock

ROOT = Path(__file__).resolve().parents[1]


class LockTests(unittest.TestCase):
    def test_independent_process_cannot_overlap_or_create_lock_file(self):
        before = set((ROOT / "jp").iterdir())
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop(LOCK_ENV, None)
        command = [sys.executable, "-m", "jp.local_lock", "--", sys.executable, "-c", "pass"]
        with execution_lock():
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("已在執行", result.stderr)
        self.assertEqual(subprocess.run(command, cwd=ROOT, env=env, capture_output=True).returncode, 0)
        self.assertEqual(set((ROOT / "jp").iterdir()), before)

    def test_inherited_lock_survives_child_context_exit(self):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop(LOCK_ENV, None)
        code = "from jp.local_lock import execution_lock;\nwith execution_lock(): pass"
        with execution_lock() as fd:
            result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                    env={**env, LOCK_ENV: str(fd)}, pass_fds=(fd,), capture_output=True)
            self.assertEqual(result.returncode, 0)
            competitor = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                        env=env, capture_output=True)
            self.assertNotEqual(competitor.returncode, 0)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.data = self.root / "private data"
        self.data.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.jsonl"
        self.env = {**os.environ, "HOME": str(self.root), "PTT_DATA_DIR": str(self.data),
                    "PTT_PYTHON": str(self.bin / "python"), "FAKE_CALLS": str(self.log),
                    "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", "")}
        self.env.pop(LOCK_ENV, None)
        self.executable("git", """
            import json, os, pathlib, sys
            args = sys.argv[3:]
            with open(os.environ['FAKE_CALLS'], 'a') as stream:
                stream.write(json.dumps(args) + '\\n')
            if args[0] == os.environ.get('FAKE_FAIL_COMMAND'): sys.exit(128)
            if args[0] == 'rev-parse': print(os.environ['PTT_DATA_DIR'])
            elif args[0] == 'remote': print(os.environ.get('FAKE_REMOTE', 'git@github.com:iPliny/ptt-iphone-data.git'))
            elif args[0] == 'branch': print('main')
            elif args[0] == 'status': print(os.environ.get('FAKE_DIRTY', ''), end='')
            elif args[0] == 'diff':
                if '--cached' in args: sys.exit(int(os.environ.get('FAKE_CHANGED', '1')))
                print(os.environ.get('FAKE_OUTSIDE', ''), end='')
            elif args[0] == 'push':
                counter = pathlib.Path(os.environ['FAKE_CALLS'] + '.count')
                count = int(counter.read_text()) if counter.exists() else 0
                counter.write_text(str(count + 1))
                sys.exit(count < int(os.environ.get('FAKE_PUSH_FAILURES', '0')))
        """)
        self.executable("python", f"""
            import json, os, sys
            if sys.argv[1:3] == ['-m', 'jp.local']:
                with open(os.environ['FAKE_CALLS'], 'a') as stream:
                    stream.write(json.dumps(['crawl', *sys.argv[3:]]) + '\\n')
                sys.exit(int(os.environ.get('FAKE_CRAWL_STATUS', '0')))
            os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
        """)

    def executable(self, name, body):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n" + textwrap.dedent(body))
        path.chmod(0o700)

    def run_script(self, **env):
        result = subprocess.run(["/bin/bash", str(ROOT / "local/run.sh")], cwd=ROOT,
                                env={**self.env, **env}, capture_output=True, text=True)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
        return result, calls

    def test_scopes_commit_and_rebases_before_retry_without_deployment(self):
        result, calls = self.run_script(FAKE_PUSH_FAILURES="1")
        self.assertEqual(result.returncode, 0)
        self.assertIn(["add", "--", "jp/"], calls)
        self.assertIn(["crawl", "--data", str(self.data / "jp")], calls)
        self.assertEqual(sum(c[0] == "pull" for c in calls), 2)
        self.assertEqual(sum(c[0] == "push" for c in calls), 2)
        self.assertTrue(next(c for c in calls if c[0] == "commit")[2].startswith("本機日本價格更新 "))
        self.assertFalse(any("dispatch" in str(c) for c in calls))
        self.assertIn("同步完成", (self.root / "Library/Logs/ptt-local-crawler.log").read_text())

    def test_no_changes_does_not_commit(self):
        result, calls = self.run_script(FAKE_CHANGED="0")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(any(c[0] == "commit" for c in calls))

    def test_failed_crawl_does_not_stage_commit_or_push(self):
        result, calls = self.run_script(FAKE_CRAWL_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0] in ("add", "commit", "push") for c in calls))
        self.assertIn("失敗", (self.root / "Library/Logs/ptt-local-crawler.log").read_text())

    def test_push_retries_three_times_then_fails(self):
        result, calls = self.run_script(FAKE_PUSH_FAILURES="10")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sum(c[0] == "push" for c in calls), 4)

    def test_dirty_clone_and_wrong_remote_stop_before_fetch(self):
        for override in ({"FAKE_DIRTY": "M jp/latest.csv"}, {"FAKE_REMOTE": "git@github.com:iPliny/ptt-iphone-tracker.git"}):
            with self.subTest(override=override):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_script(**override)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(c[0] in ("pull", "crawl", "push") for c in calls))

    def test_unpushed_non_jp_commit_stops_before_crawl(self):
        result, calls = self.run_script(FAKE_OUTSIDE="listings.csv")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0] in ("crawl", "add", "commit", "push") for c in calls))

    def test_git_status_and_diff_errors_are_not_treated_as_clean(self):
        for override in ({"FAKE_FAIL_COMMAND": "status"}, {"FAKE_FAIL_COMMAND": "diff"}, {"FAKE_CHANGED": "128"}):
            with self.subTest(override=override):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_script(**override)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(c[0] in ("commit", "push") for c in calls))

    def test_launchd_template_has_two_daily_times(self):
        config = plistlib.loads((ROOT / "local/com.crawlsnek.ptt-local-crawler.plist").read_bytes())
        self.assertEqual(config["StartCalendarInterval"], [{"Hour": 9, "Minute": 40}, {"Hour": 21, "Minute": 40}])
        self.assertNotIn("RunAtLoad", config)
