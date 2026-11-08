"""只在暫存 HOME 測試，絕不觸碰實際排程或私人 clone。"""
import os
import fcntl
import sys
from pathlib import Path
import plistlib
import subprocess

import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "local/bootstrap.sh"


def shell(home, command):
    env = {**os.environ, "HOME": str(home),
           "PTT_LOCAL_LOCK_PATH": str(home / "Library/Application Support/crawlsnek/ptt-local-crawler.lock")}
    env.pop("PTT_LOCAL_LOCK_FD", None)
    return subprocess.run(["/bin/bash", "-c", 'source "$1"; timed() { shift; "$@"; }; ' + command, "test", str(BOOT)],
                          env=env, text=True, capture_output=True)


def clones(base, wrong=False):
    for name in ("ptt-iphone-tracker", "ptt-iphone-data"):
        repo = base / name
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        origin = "other" if wrong else name
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin",
                        f"https://github.com/iPliny/{origin}.git"], check=True)
    return base


def config(home, base):
    target = home / "Library/Application Support/crawlsnek/ptt-local-crawler.conf"
    target.parent.mkdir(parents=True)
    target.write_text(f"BASE={base}\nBASE_EXISTED=1\n")
    return target



class LocalBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def test_relocate_missing_base(self):
        tmp_path = self.home
        for relative in ['ai-cowork/ptt-local-crawler', 'ptt-local-crawler', 'some folder/nested/ptt-local-crawler']:
            tmp_path = self.home / relative.replace("/", "_")
            tmp_path.mkdir()
            base = clones(tmp_path / relative)
            conf = config(tmp_path, tmp_path / "gone")
            result = shell(tmp_path, 'locate_base; printf "BASE:%s" "$BASE"')
            assert result.returncode == 0, result.stderr
            assert f"BASE:{base}" in result.stdout
            assert conf.read_text() == f"BASE={base}\nBASE_EXISTED=1\n"

    def test_configured_base_has_priority_and_spaces(self):
        tmp_path = self.home
        base = clones(tmp_path / "custom space/runner")
        clones(tmp_path / "ai-cowork/ptt-local-crawler")
        config(tmp_path, base)
        result = shell(tmp_path, 'locate_base; printf "%s" "$BASE"')
        assert result.returncode == 0
        assert result.stdout == str(base)

    def test_tcc_and_symlink_rejected(self):
        tmp_path = self.home
        for protected in ['Documents', 'Desktop', 'Downloads', 'documents', 'Library', '.Trash']:
            tmp_path = self.home / ("case_" + str(len(list(self.home.iterdir()))))
            tmp_path.mkdir()
            base = clones(tmp_path / protected / "ptt-local-crawler")
            link = tmp_path / "shortcut"
            link.symlink_to(base, target_is_directory=True)
            for candidate in (base, link, link / "missing"):
                result = shell(tmp_path, f'allowed_path "{candidate}"')
                assert result.returncode != 0

    def test_find_skips_tcc_wrong_origin_and_too_deep(self):
        tmp_path = self.home
        clones(tmp_path / "Documents/ptt-local-crawler")
        clones(tmp_path / "Desktop/ptt-local-crawler")
        clones(tmp_path / "Downloads/ptt-local-crawler")
        clones(tmp_path / "ai-cowork/ptt-local-crawler", wrong=True)
        clones(tmp_path / "a/b/c/d/e/ptt-local-crawler")
        good = clones(tmp_path / "other/ptt-local-crawler")
        result = shell(tmp_path, 'locate_base; printf "BASE:%s" "$BASE"')
        assert result.returncode == 0
        assert f"BASE:{good}" in result.stdout

    def test_wrong_push_origin_rejected(self):
        tmp_path = self.home
        base = clones(tmp_path / "ptt-local-crawler")
        subprocess.run(["git", "-C", str(base / "ptt-iphone-data"), "remote", "set-url", "--push",
                        "origin", "https://github.com/iPliny/other.git"], check=True)
        assert shell(tmp_path, f'valid_base "{base}"').returncode != 0

    def test_no_match_clones_both_and_saves_config(self):
        tmp_path = self.home
        # 替身 clone 不連網；沿用真正 origin 驗證。
        result = shell(tmp_path, '''
            git() {
                if [ "$1" = clone ]; then
                    command git init -q "$3"
                    command git -C "$3" remote add origin "$2"
                else command git "$@"; fi
            }
            locate_base
            valid_base "$BASE"
        ''')
        assert result.returncode == 0, result.stderr
        conf = tmp_path / "Library/Application Support/crawlsnek/ptt-local-crawler.conf"
        assert conf.read_text() == f"BASE={tmp_path}/ai-cowork/ptt-local-crawler\nBASE_EXISTED=1\n"

    def test_does_not_overwrite_invalid_clone(self):
        tmp_path = self.home
        clones(tmp_path / "ai-cowork/ptt-local-crawler", wrong=True)
        result = shell(tmp_path, 'locate_base')
        assert result.returncode != 0
        assert "不覆寫" in result.stdout

    def test_pull_failure_still_executes_with_base_environment(self):
        tmp_path = self.home
        base = clones(tmp_path / "ptt-local-crawler")
        code = base / "ptt-iphone-tracker"
        (code / ".venv/bin").mkdir(parents=True)
        python = code / ".venv/bin/python"
        python.write_text("#!/bin/bash\nexit 0\n")
        python.chmod(0o700)
        (code / "requirements.txt").write_text("# test\n")
        (code / ".venv/ptt-requirements.txt").write_text("# test\n")
        (code / "local").mkdir()
        (code / "local/run.sh").write_text('printf "%s\\n%s\\n" "$PTT_DATA_DIR" "$PTT_PYTHON" > "$HOME/result"\n')
        result = shell(tmp_path, '''git() {
            if [ "$3" = pull ]; then return 1; else command git "$@"; fi
        }; main''')
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "result").read_text().splitlines() == [str(base / "ptt-iphone-data"), str(python)]
        assert "pull 失敗" in (tmp_path / "Library/Logs/ptt-local-crawler.log").read_text()

    def test_busy_bootstrap_never_pulls_or_installs(self):
        lock = self.home / "Library/Application Support/crawlsnek/ptt-local-crawler.lock"
        lock.parent.mkdir(parents=True)
        with lock.open("w+") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = shell(self.home, 'git() { echo "$*" >> "$HOME/git-calls"; }; main')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / "git-calls").exists())
        self.assertIn("正在執行", (self.home / "Library/Logs/ptt-local-crawler.log").read_text())

    def test_bootstrap_passes_held_lock_through_run_to_python(self):
        base = clones(self.home / "runner")
        config(self.home, base)
        code = base / "ptt-iphone-tracker"
        (code / ".venv/bin").mkdir(parents=True)
        (code / ".venv/bin/python").symlink_to(sys.executable)
        (code / "requirements.txt").write_text("")
        (code / ".venv/ptt-requirements.txt").write_text("")
        (code / "local").mkdir()
        (code / "local/run.sh").write_text(
            'cd "' + str(ROOT) + '"\n"$PTT_PYTHON" -m jp.local_lock --check\n'
            'if env -u PTT_LOCAL_LOCK_FD "$PTT_PYTHON" -m jp.local_lock -- /usr/bin/true; then exit 9; fi\n'
            '"$PTT_PYTHON" -c \'import os; from jp.local_lock import execution_lock; '
            'from pathlib import Path; '
            'ctx=execution_lock(); ctx.__enter__(); Path(os.environ["HOME"], "held").touch()\'\n')
        result = shell(self.home, 'git() { if [ "$3" = pull ]; then return 0; else command git "$@"; fi; }; main')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.home / "held").exists())

    def test_plist_has_stable_entry_and_original_schedule(self):
        data = plistlib.loads((ROOT / "local/com.crawlsnek.ptt-local-crawler.plist").read_bytes())
        assert data["ProgramArguments"] == ["/bin/bash", "__BOOTSTRAP__"]
        assert "WorkingDirectory" not in data
        assert data["StartCalendarInterval"] == [{"Hour": 9, "Minute": 40}, {"Hour": 21, "Minute": 40}]

    def test_existing_config_missing_never_clones(self):
        conf = config(self.home, self.home / 'gone')
        result = shell(self.home, 'git() { echo UNEXPECTED_CLONE; return 1; }; locate_base')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('UNEXPECTED_CLONE', result.stdout)
        self.assertIn('嚴重錯誤', result.stderr)
        self.assertIn('BASE_EXISTED=1', conf.read_text())

    def test_unprovisioned_config_may_clone_but_existing_directory_may_not(self):
        conf = config(self.home, self.home / 'new')
        conf.write_text(f'BASE={self.home}/new\nBASE_EXISTED=0\n')
        result = shell(self.home, '''git() {
            if [ "$1" = clone ]; then command git init -q "$3"; command git -C "$3" remote add origin "$2";
            else command git "$@"; fi
        }; locate_base''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('BASE_EXISTED=1', conf.read_text())
        conf.write_text(f'BASE={self.home}/invalid\nBASE_EXISTED=0\n')
        (self.home / 'invalid').mkdir()
        # Remove valid alternative to exercise invalid existing BASE.
        import shutil
        shutil.rmtree(self.home / 'new')
        result = shell(self.home, 'locate_base')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('嚴重錯誤', result.stderr)

    def test_multiple_candidates_choose_latest_data_commit_and_log_all(self):
        older = clones(self.home / 'old arbitrary name')
        newer = clones(self.home / 'nested/new arbitrary name')
        for base, stamp in [(older, '2026-10-01T00:00:00+09:00'), (newer, '2026-11-01T00:00:00+09:00')]:
            subprocess.run(['git', '-C', str(base / 'ptt-iphone-data'), '-c', 'user.name=Test',
                            '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'fixture'],
                           env={**os.environ, 'GIT_AUTHOR_DATE': stamp, 'GIT_COMMITTER_DATE': stamp}, check=True)
        result = shell(self.home, 'locate_base; printf "CHOSEN:%s" "$BASE"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'有效候選：{older}', result.stdout)
        self.assertIn(f'有效候選：{newer}', result.stdout)
        self.assertIn(f'CHOSEN:{newer}', result.stdout)

    def test_clone_failure_logs_and_does_not_save_conf(self):
        result = shell(self.home, 'git() { return 42; }; main')
        self.assertEqual(result.returncode, 42)
        self.assertFalse((self.home / 'Library/Application Support/crawlsnek/ptt-local-crawler.conf').exists())
        self.assertTrue((self.home / 'Library/Logs/ptt-local-crawler.log').exists())

    def test_main_creates_venv_retries_failed_pip_then_runs(self):
        base = clones(self.home / 'runner')
        config(self.home, base)
        code = base / 'ptt-iphone-tracker'
        (code / 'requirements.txt').write_text('fixture\n')
        (code / 'local').mkdir()
        (code / 'local/run.sh').write_text('touch "$HOME/ran"\n')
        fake = self.home / 'fake-python'
        fake.write_text('''#!/bin/bash
if [ "$2" = venv ]; then
    mkdir -p "$3/bin"
    cp "$0" "$3/bin/python"
    exit 0
fi
if [ -e "$HOME/fail-pip" ]; then exit 9; fi
touch "$HOME/pip-ok"
''')
        fake.chmod(0o700)
        (self.home / 'fail-pip').touch()
        command = f'''find_python() {{ printf '%s' '{fake}'; }};
            git() {{ if [ "$3" = pull ]; then return 0; else command git "$@"; fi; }}; main'''
        first = shell(self.home, command)
        self.assertEqual(first.returncode, 9)
        self.assertFalse((code / '.venv/ptt-requirements.txt').exists())
        self.assertFalse((self.home / 'ran').exists())
        (self.home / 'fail-pip').unlink()
        second = shell(self.home, command)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue((self.home / 'pip-ok').exists())
        self.assertTrue((self.home / 'ran').exists())
        self.assertEqual((code / '.venv/ptt-requirements.txt').read_text(), 'fixture\n')

    def install_fixture(self):
        # 只執行暫存副本，以假 launchctl 隔離主機排程。
        import shutil
        stage = self.home / 'source'
        (stage / 'local').mkdir(parents=True)
        for name in ('install.sh', 'bootstrap.sh', 'com.crawlsnek.ptt-local-crawler.plist'):
            shutil.copy(ROOT / 'local' / name, stage / 'local' / name)
        base = clones(self.home / 'runner')
        lock = self.home / "test-lock/runner.lock"
        lock.parent.mkdir()
        lock.touch()
        bindir = self.home / 'bin'
        bindir.mkdir()
        scripts = {
            'launchctl': '''#!/bin/bash
echo "$*" >> "$HOME/launch-calls"
case "$1" in
 print) if [ -e "$HOME/running" ]; then echo 'state = running'; else echo 'state = waiting'; fi ;;
 bootstrap)
    n=$(cat "$HOME/attempts" 2>/dev/null || echo 0)
    n=$((n + 1)); echo "$n" > "$HOME/attempts"
    [ "$n" -gt 2 ] ;;
esac
''',
            'plutil': '#!/bin/bash\nexit 0\n',
            'sleep': '#!/bin/bash\nexit 0\n',
        }
        for name, text in scripts.items():
            path = bindir / name
            path.write_text(text)
            path.chmod(0o700)
        def run(path=base):
            return subprocess.run(['/bin/bash', str(stage / 'local/install.sh'), str(path)],
                                  env={**os.environ, 'HOME': str(self.home), 'PTT_LOCAL_LOCK_PATH': str(lock), 'PATH': f'{bindir}:' + os.environ['PATH']},
                                  capture_output=True, text=True, timeout=30)
        return base, lock, run

    def test_install_is_idempotent_and_retries_bootstrap(self):
        base, _, run = self.install_fixture()
        for _ in range(2):
            result = run()
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / 'attempts').read_text().strip(), '4')
        conf = self.home / 'Library/Application Support/crawlsnek/ptt-local-crawler.conf'
        self.assertEqual(conf.read_text(), f'BASE={base}\nBASE_EXISTED=1\n')
        plist = plistlib.loads((self.home / 'Library/LaunchAgents/com.crawlsnek.ptt-local-crawler.plist').read_bytes())
        self.assertEqual(plist['ProgramArguments'], ['/bin/bash', str(self.home / 'Library/Application Support/crawlsnek/ptt-bootstrap.sh')])
        self.assertEqual(plist['StartCalendarInterval'], [{'Hour': 9, 'Minute': 40}, {'Hour': 21, 'Minute': 40}])
        calls = (self.home / 'launch-calls').read_text()
        self.assertNotIn('kickstart', calls)
        self.assertEqual(calls.count('bootout '), 2)

    def test_install_rejects_invalid_path_and_running_job_before_writing(self):
        base, lock, run = self.install_fixture()
        invalid = run(self.home / 'typo')
        self.assertNotEqual(invalid.returncode, 0)
        self.assertFalse((self.home / 'Library').exists())
        (self.home / 'running').touch()
        active = run()
        self.assertNotEqual(active.returncode, 0)
        self.assertIn('正在執行', active.stderr)
        self.assertNotIn('bootout', (self.home / 'launch-calls').read_text())
        (self.home / 'running').unlink()
        import fcntl
        with lock.open() as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            active = run()
        self.assertNotEqual(active.returncode, 0)
        self.assertIn('正在執行', active.stderr)
        self.assertFalse((self.home / 'Library').exists())

    def test_install_reports_exhausted_bootstrap_retries(self):
        _, _, run = self.install_fixture()
        (self.home / 'attempts').write_text('-10')
        result = run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('排程重新載入失敗', result.stderr)
        self.assertEqual((self.home / 'attempts').read_text().strip(), '-6')


    def test_timeout_stops_hung_external_command(self):
        result = subprocess.run(["/bin/bash", "-c", 'source "$1"; timed 1 /bin/sleep 10', "test", str(BOOT)],
                                env={**os.environ, "HOME": str(self.home)}, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)

    def test_python_selection_falls_back_in_order(self):
        for selected in ('/opt/homebrew/bin/python3', '/usr/local/bin/python3', '/usr/bin/python3'):
            result = shell(self.home, """
                [() { if builtin [ "$1" = -x ]; then builtin [ "$2" = SELECTED ]; else builtin [ "$@"; fi; }
                find_python
            """.replace('SELECTED', selected))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), selected)
