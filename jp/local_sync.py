"""本機資料同步：只自動合併 append-only 執行紀錄，其他衝突回復同步前狀態。"""
import csv
import io
from pathlib import Path
import subprocess
import sys

from .buyback import RUN_FIELDS

RUN_PATHS = {"jp/runs.csv", "jp/local/runs.csv", "jp/sell/runs.csv"}


def git(root, *args, check=True):
    return subprocess.run(["git", "-C", str(root), *args], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def operation_path(root, name):
    path = Path(git(root, "rev-parse", "--git-path", name).stdout.strip())
    return path if path.is_absolute() else Path(root) / path


def rebasing(root):
    return any(operation_path(root, name).exists() for name in ("rebase-merge", "rebase-apply"))


def check_state(root):
    for name, operation in (("rebase-merge", "rebase"), ("rebase-apply", "rebase"),
                            ("MERGE_HEAD", "merge")):
        if operation_path(root, name).exists():
            result = git(root, operation, "--abort", check=False)
            if result.returncode:
                raise RuntimeError(f"殘留 {operation} 中止失敗，停止同步；請人工檢查")
            print(f"已中止殘留 {operation}，回復原本分支狀態，繼續同步", flush=True)
    for name in ("CHERRY_PICK_HEAD", "REVERT_HEAD"):
        if operation_path(root, name).exists():
            raise RuntimeError(f"私人資料庫殘留 {name}；請先人工處理")


def read_runs(value):
    rows = list(csv.reader(io.StringIO(value)))
    if not rows and not value:
        return []
    if not rows or rows[0] != list(RUN_FIELDS) or any(len(r) != len(RUN_FIELDS) for r in rows[1:]):
        raise ValueError("runs.csv 欄位不符，停止自動合併")
    return [tuple(r) for r in rows[1:]]


def commit_pending_failures(root):
    entries = git(root, "status", "--porcelain", "-z", "--untracked-files=all").stdout.split("\0")
    paths = []
    for entry in filter(None, entries):
        status, path = entry[:2], entry[3:]
        if path not in RUN_PATHS or status not in (" M", "M ", "MM", "A ", "AM", "??"):
            raise RuntimeError("私人資料庫有非失敗紀錄的未提交變更，停止同步")
        target = Path(root) / path
        if target.is_symlink():
            raise RuntimeError("執行紀錄不可為符號連結")
        previous = git(root, "show", f"HEAD:{path}", check=False)
        if previous.returncode:
            # 只有 HEAD 確實沒有此路徑時才當作新檔，其他 Git 錯誤照常停止。
            if git(root, "ls-tree", "HEAD", "--", path).stdout.strip():
                raise RuntimeError("無法讀取原執行紀錄")
        original = read_runs(previous.stdout if previous.returncode == 0 else "")
        current = read_runs(target.read_text(encoding="utf-8"))
        added = current[len(original):]
        if current[:len(original)] != original or not added or any(
                row[RUN_FIELDS.index("status")] not in ("fetch_error", "parse_error") for row in added):
            raise RuntimeError("未提交執行紀錄並非只追加失敗紀錄，停止同步")
        # 已暫存版本也必須只是相同失敗紀錄的追加，避免覆蓋其他 staged 編輯。
        staged = git(root, "show", f":{path}", check=False)
        if staged.returncode == 0:
            indexed = read_runs(staged.stdout)
            if indexed != current[:len(indexed)] or indexed[:len(original)] != original:
                raise RuntimeError("暫存執行紀錄與工作目錄不一致，停止同步")
        paths.append(path)
    if paths:
        git(root, "add", "--", *sorted(paths))
        git(root, "commit", "-m", "補存本機日本價格抓取失敗紀錄")
        print("已提交殘留的抓取失敗紀錄，繼續同步", flush=True)


def merge_runs(base, ours, theirs):
    original, left, right = map(read_runs, (base, ours, theirs))
    if not set(original) <= set(left) or not set(original) <= set(right):
        raise ValueError("runs.csv 不是只追加，停止自動合併")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(RUN_FIELDS)
    writer.writerows(dict.fromkeys(left + right))
    return output.getvalue()


def sync(root):
    check_state(root)
    git(root, "fetch", "origin", "main")
    result = git(root, "rebase", "origin/main", check=False)
    try:
        while result.returncode:
            paths = git(root, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
            if not paths or not set(paths) <= RUN_PATHS:
                raise RuntimeError("rebase 遇到非執行紀錄衝突或其他錯誤；保留原本 commit，停止同步")
            for path in paths:
                versions = []
                for stage in (1, 2, 3):
                    blob = git(root, "show", f":{stage}:{path}", check=False)
                    if blob.returncode and stage != 1:
                        raise RuntimeError("紀錄遭刪除，停止自動合併")
                    versions.append(blob.stdout if blob.returncode == 0 else "")
                merged = merge_runs(*versions)
                (Path(root) / path).write_text(merged, encoding="utf-8", newline="")
                git(root, "add", "--", path)
            result = git(root, "-c", "core.editor=true", "rebase", "--continue", check=False)
    except Exception as exc:
        try:
            if rebasing(root):
                aborted = git(root, "rebase", "--abort", check=False)
                if aborted.returncode:
                    print(f"rebase 中止失敗，請人工檢查；原始錯誤：{exc}", file=sys.stderr)
        except Exception as cleanup_error:
            print(f"rebase 復原檢查失敗：{cleanup_error}；原始錯誤：{exc}", file=sys.stderr)
        raise


def main():
    try:
        {"check": check_state, "prepare": commit_pending_failures, "sync": sync}[sys.argv[1]](Path(sys.argv[2]))
    except (RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"本機同步停止：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
