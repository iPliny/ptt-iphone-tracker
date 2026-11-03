"""停更回歸測試：只用合成資料與暫存 Git repo，不接觸私人資料庫。"""
import contextlib
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jp import buyback as jp, local, local_sync
from tests.test_jp_buyback import shop_page
from tests.test_jp_local import pastec_result

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "site"))
from jp_build import buyback_sources

T0 = "2026-11-01T09:40:00+09:00"
T1 = "2026-11-02T09:40:00+09:00"
T2 = "2026-11-03T09:40:00+09:00"


class OwnershipTests(unittest.TestCase):
    def test_live_fixture_still_matches_existing_parser(self):
        html = (Path(__file__).parent / "fixtures/jp/iosys-live-20261103.html").read_text()
        rows, _ = jp.parse_iosys(html, jp.IOSYS_URLS[0])
        self.assertEqual(len(rows), 40)
        self.assertEqual({r["model"] for r in rows}, {"iPhone 18 Pro"})


    def test_local_iosys_uses_buyback_pages_and_preserves_cloud_files(self):
        calls = []
        def fetch(url):
            calls.append(url)
            return shop_page(url)
        results = local.collect(("iosys-buyback",), fetch)
        self.assertEqual(calls, list(jp.IOSYS_URLS))
        self.assertEqual(results[0]["status"], "ok")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jp.apply_results(root, results, T0)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            local.save_or_check(root, results, run_at=T1)
            for name, value in before.items():
                self.assertEqual((root / name).read_bytes(), value)
            original = buyback_sources(root)
            changed = dict(results[0], rows=[dict(r, price_jpy=r["price_jpy"] + 5000) for r in results[0]["rows"]])
            jp.apply_results(root, [changed], T2)
            self.assertEqual(buyback_sources(root), original)
            failed = dict(results[0], status="fetch_error", error="HTTP 403", rows=[])
            local.save_or_check(root, [failed], run_at=T2)
            after = buyback_sources(root)
            self.assertEqual(after["latest"], original["latest"])
            self.assertEqual(after["runs"][-1]["status"], "fetch_error")

    def test_migration_retains_since_and_no_fake_price_event_next_run(self):
        result = pastec_result()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jp.apply_results(root, [result], T0)
            local.save_or_check(root, [result], run_at=T1)
            before = (root / "local/prices.csv").read_bytes()
            local.save_or_check(root, [result], run_at=T2)
            self.assertEqual((root / "local/prices.csv").read_bytes(), before)
            self.assertEqual({r["since"] for r in jp.read_csv(root / "local/latest.csv")}, {T0})
            self.assertEqual(len(buyback_sources(root)["prices"]), len(result["rows"]))

    def test_first_local_failure_keeps_legacy_and_validates_legacy_count(self):
        result = pastec_result()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jp.apply_results(root, [result], T0)
            before = buyback_sources(root)["latest"]
            bad = dict(result, rows=result["rows"][:1])
            reports = local.save_or_check(root, [bad], run_at=T1)
            self.assertEqual(reports[0]["status"], "parse_error")
            self.assertEqual(buyback_sources(root)["latest"], before)
            self.assertFalse((root / "local/latest.csv").exists())

    def test_http_diagnostics_without_response_or_secrets(self):
        exc = jp.requests.RequestsError("HTTP Error 403 secret URL https://example.com/?token=secret")
        exc.response = type("Response", (), {"status_code": 403})()
        self.assertIn("HTTP 403", jp.fetch_error(exc))
        self.assertNotIn("secret", jp.fetch_error(exc))
        self.assertIn("連線逾時", jp.fetch_error(RuntimeError("curl: (28) timed out token=secret")))
        self.assertIn("curl error 28", jp.fetch_error(RuntimeError("curl: (28) timed out token=secret")))
        results = jp.collect(lambda url: (_ for _ in ()).throw(exc), only=("イオシス",))
        output = io.StringIO()
        with patch.object(sys, "argv", ["buyback", "--dry-run"]), patch.object(jp, "collect", return_value=results), contextlib.redirect_stdout(output):
            self.assertEqual(jp.main(), 1)
        self.assertIn("HTTP 403", json.loads(output.getvalue())[0]["error"])


def run_csv(*labels):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(jp.RUN_FIELDS)
    for label in labels:
        writer.writerow([T0, "モバステ", "fetch_error", 0, label])
    return out.getvalue()


class SyncTests(unittest.TestCase):
    def test_union_preserves_multiline_csv_and_rejects_edits(self):
        result = local_sync.merge_runs(run_csv("base"), run_csv("base", "one,\nline"), run_csv("base", "two", "one,\nline"))
        self.assertEqual(result, run_csv("base", "one,\nline", "two"))
        with self.assertRaises(ValueError):
            local_sync.merge_runs(run_csv("base"), run_csv("changed"), run_csv("base"))

    def setup_repos(self, root):
        def cmd(*args, cwd=None):
            return subprocess.run(["git", *map(str, args)], cwd=cwd, check=True, capture_output=True, text=True)
        remote, left, right = (root / n for n in ("remote.git", "left", "right"))
        cmd("init", "--bare", "--initial-branch=main", remote)
        cmd("clone", remote, left)
        def identity(path):
            cmd("config", "user.name", "Fixture", cwd=path)
            cmd("config", "user.email", "fixture@example.invalid", cwd=path)
        identity(left)
        (left / "jp").mkdir()
        (left / "jp/runs.csv").write_text(run_csv("base"))
        cmd("add", ".", cwd=left); cmd("commit", "-m", "fixture base", cwd=left)
        cmd("push", "origin", "main", cwd=left)
        cmd("clone", remote, right); identity(right)
        return cmd, left, right

    def test_real_rebase_merges_append_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd, left, right = self.setup_repos(Path(tmp))
            for repo, label in ((left, "local"), (right, "actions")):
                (repo / "jp/runs.csv").write_text(run_csv("base", label))
                cmd("add", ".", cwd=repo); cmd("commit", "-m", label, cwd=repo)
            cmd("push", "origin", "main", cwd=right)
            local_sync.sync(left)
            self.assertEqual(set(r["error"] for r in jp.read_csv(left / "jp/runs.csv")), {"base", "local", "actions"})
            self.assertEqual(cmd("status", "--porcelain", cwd=left).stdout, "")
            cmd("push", "origin", "main", cwd=left)  # 正常 fast-forward，無 force。

    def test_unresolvable_conflict_aborts_only_own_rebase(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd, left, right = self.setup_repos(Path(tmp))
            for repo, label in ((left, "local-edit"), (right, "remote-edit")):
                (repo / "jp/runs.csv").write_text(run_csv(label))
                cmd("add", ".", cwd=repo); cmd("commit", "-m", label, cwd=repo)
            cmd("push", "origin", "main", cwd=right)
            head = cmd("rev-parse", "HEAD", cwd=left).stdout
            with self.assertRaises(ValueError):
                local_sync.sync(left)
            self.assertEqual(cmd("rev-parse", "HEAD", cwd=left).stdout, head)
            self.assertEqual(cmd("status", "--porcelain", cwd=left).stdout, "")

    def test_stale_operations_abort_and_restore_branch(self):
        for operation in ("rebase", "merge"):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as tmp:
                cmd, left, right = self.setup_repos(Path(tmp))
                for repo, label in ((left, "local"), (right, "remote")):
                    (repo / "jp/runs.csv").write_text(run_csv("base", label))
                    cmd("add", ".", cwd=repo)
                    cmd("commit", "-m", label, cwd=repo)
                cmd("push", "origin", "main", cwd=right)
                cmd("fetch", "origin", cwd=left)
                head = cmd("rev-parse", "HEAD", cwd=left).stdout
                with self.assertRaises(subprocess.CalledProcessError):
                    cmd(operation, "origin/main", cwd=left)
                log = io.StringIO()
                with contextlib.redirect_stdout(log):
                    local_sync.check_state(left)
                self.assertIn(f"已中止殘留 {operation}", log.getvalue())
                self.assertEqual(cmd("rev-parse", "HEAD", cwd=left).stdout, head)
                self.assertEqual(cmd("branch", "--show-current", cwd=left).stdout.strip(), "main")
                self.assertEqual(cmd("status", "--porcelain", cwd=left).stdout, "")
                local_sync.sync(left)
                self.assertEqual(local_sync.read_runs((left / "jp/runs.csv").read_text()),
                                 local_sync.read_runs(run_csv("base", "remote", "local")))

    def test_multiple_local_commits_preserve_order_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            cmd, left, right = self.setup_repos(Path(tmp))
            for labels in (("base", "one"), ("base", "one", "two")):
                (left / "jp/runs.csv").write_text(run_csv(*labels))
                cmd("add", ".", cwd=left)
                cmd("commit", "-m", labels[-1], cwd=left)
            (right / "jp/runs.csv").write_text(run_csv("base", "remote"))
            cmd("add", ".", cwd=right)
            cmd("commit", "-m", "remote", cwd=right)
            cmd("push", "origin", "main", cwd=right)
            local_sync.sync(left)
            self.assertEqual(local_sync.read_runs((left / "jp/runs.csv").read_text()),
                             local_sync.read_runs(run_csv("base", "remote", "one", "two")))
            self.assertEqual(cmd("status", "--porcelain", cwd=left).stdout, "")
            cmd("push", "origin", "main", cwd=left)

    def test_pending_failures_only_are_committed(self):
        for kind in ("failure", "new", "success", "edit", "other", "staged-edit"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                cmd, left, _ = self.setup_repos(Path(tmp))
                path = left / "jp/runs.csv"
                if kind == "new":
                    path = left / "jp/local/runs.csv"
                    path.parent.mkdir()
                path.write_text(run_csv("new") if kind == "new" else run_csv("base", "failure"))
                if kind == "success":
                    path.write_text(run_csv("base") + run_csv("ok").splitlines(True)[1].replace("fetch_error", "ok"))
                if kind == "edit":
                    path.write_text(run_csv("changed"))
                if kind == "other":
                    (left / "jp/latest.csv").write_text("unexpected")
                if kind == "staged-edit":
                    path.write_text(run_csv("changed"))
                    cmd("add", ".", cwd=left)
                    path.write_text(run_csv("base", "failure"))
                head = cmd("rev-parse", "HEAD", cwd=left).stdout
                if kind in ("failure", "new"):
                    local_sync.commit_pending_failures(left)
                    self.assertNotEqual(cmd("rev-parse", "HEAD", cwd=left).stdout, head)
                    self.assertEqual(cmd("status", "--porcelain", cwd=left).stdout, "")
                else:
                    with self.assertRaises((RuntimeError, ValueError)):
                        local_sync.commit_pending_failures(left)
                    self.assertEqual(cmd("rev-parse", "HEAD", cwd=left).stdout, head)

    def test_abort_failure_stops_and_no_rebase_keeps_original_error(self):
        with patch.object(local_sync, "operation_path") as path, patch.object(local_sync, "git") as git:
            path.return_value.exists.return_value = True
            git.return_value.returncode = 1
            with self.assertRaisesRegex(RuntimeError, "中止失敗"):
                local_sync.check_state("unused")
            self.assertEqual(git.call_count, 1)
        with patch.object(local_sync, "check_state"), patch.object(local_sync, "rebasing", return_value=False), patch.object(local_sync, "git") as git:
            git.side_effect = [None, subprocess.CompletedProcess([], 1), RuntimeError("original failure")]
            with self.assertRaisesRegex(RuntimeError, "original failure"):
                local_sync.sync("unused")
            self.assertFalse(any("--abort" in call.args for call in git.call_args_list))

    def test_cleanup_failure_does_not_mask_original_error(self):
        for cleanup in ("abort", "inspection"):
            with self.subTest(cleanup=cleanup), patch.object(local_sync, "check_state"), patch.object(local_sync, "rebasing") as rebasing, patch.object(local_sync, "git") as git:
                rebasing.return_value = True
                if cleanup == "inspection":
                    rebasing.side_effect = RuntimeError("inspection failure")
                git.side_effect = [None, subprocess.CompletedProcess([], 1),
                                   RuntimeError("original failure"), subprocess.CompletedProcess([], 1)]
                log = io.StringIO()
                with contextlib.redirect_stderr(log), self.assertRaisesRegex(RuntimeError, "original failure"):
                    local_sync.sync("unused")
                self.assertIn("原始錯誤：original failure", log.getvalue())
