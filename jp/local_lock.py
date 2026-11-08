"""本機爬蟲與 Git 同步共用的檔案鎖；使用 checkout 外的固定鎖檔。"""
from __future__ import annotations

import contextlib
import fcntl
import os
from pathlib import Path
import sys

LOCK_ENV = "PTT_LOCAL_LOCK_FD"
LOCK_PATH_ENV = "PTT_LOCAL_LOCK_PATH"


def lock_path():
    return Path(os.environ.get(LOCK_PATH_ENV, str(
        Path.home() / "Library/Application Support/crawlsnek/ptt-local-crawler.lock"))).expanduser()


class AlreadyRunning(RuntimeError):
    """已有本機爬蟲執行，或繼承的鎖無效。"""


@contextlib.contextmanager
def execution_lock():
    inherited = os.environ.get(LOCK_ENV)
    owned = inherited is None
    try:
        path = lock_path()
        if owned:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.parent.chmod(0o700)
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            os.fchmod(fd, 0o600)
        else:
            fd = int(inherited)
        actual, expected = os.fstat(fd), path.stat()
        if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
            raise ValueError("鎖的檔案不符")
        if not owned:
            # 獨立 open 必須被擋住，且同一 open-file description 再取鎖須成功。
            with path.open("rb") as probe:
                try:
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    raise ValueError("繼承的 fd 未持鎖")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ValueError) as exc:
        if owned and "fd" in locals():
            os.close(fd)
        raise AlreadyRunning("本機爬蟲已在執行，或繼承的檔案鎖無效") from exc
    try:
        yield fd
    finally:
        # 子程序沿用相同 open-file description，不可解開父程序的鎖。
        if owned:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--check"]:
        if LOCK_ENV not in os.environ:
            return 1
        with execution_lock():
            return 0
    if not args or args[0] != "--" or len(args) == 1:
        raise ValueError("用法：python -m jp.local_lock -- 指令 [參數]")
    with execution_lock() as fd:
        os.set_inheritable(fd, True)
        env = {**os.environ, LOCK_ENV: str(fd)}
        os.execvpe(args[1], args[1:], env)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AlreadyRunning, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
