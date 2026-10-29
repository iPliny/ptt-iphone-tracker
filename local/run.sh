#!/bin/bash
# 家用 Mac：只同步私人資料庫的 jp/，不觸發部署。
set -euo pipefail
umask 077

mkdir -p "$HOME/Library/Logs"
exec >> "$HOME/Library/Logs/ptt-local-crawler.log" 2>&1
trap 'status=$?; if [ "$status" -ne 0 ]; then printf "%s 本機日本價格更新失敗（exit %s）\n" "$(TZ=Asia/Tokyo date +%FT%T%z)" "$status"; fi' EXIT

CODE_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
cd "$CODE_DIR"
if [ -z "${PTT_PYTHON:-}" ]; then
    if [ -x "$CODE_DIR/.venv/bin/python" ]; then
        PTT_PYTHON="$CODE_DIR/.venv/bin/python"
    else
        PTT_PYTHON="$(command -v python3)"
    fi
fi
export PTT_PYTHON PYTHONDONTWRITEBYTECODE=1

if [ "$#" -eq 0 ]; then
    exec "$PTT_PYTHON" -m jp.local_lock -- /bin/bash "$CODE_DIR/local/run.sh" --locked
fi
if [ "$#" -ne 1 ] || [ "$1" != "--locked" ]; then
    printf 'run.sh 不接受參數；單獨試跑請使用 python -m jp.local --dry-run。\n'
    exit 1
fi
"$PTT_PYTHON" -m jp.local_lock --check

PTT_DATA_DIR="${PTT_DATA_DIR:-$HOME/Documents/Codex/dispatch/ptt-iphone-data}"
PTT_DATA_DIR="$(cd "$PTT_DATA_DIR" && pwd -P)"
export GIT_TERMINAL_PROMPT=0
top="$(git -C "$PTT_DATA_DIR" rev-parse --show-toplevel)"
if [ "$top" != "$PTT_DATA_DIR" ] || [ "$PTT_DATA_DIR" = "$CODE_DIR" ]; then
    printf 'PTT_DATA_DIR 必須指向獨立的私人資料庫根目錄。\n'
    exit 1
fi
for remote in "$(git -C "$PTT_DATA_DIR" remote get-url --all origin)" "$(git -C "$PTT_DATA_DIR" remote get-url --push --all origin)"; do
    case "${remote%.git}" in
        https://github.com/iPliny/ptt-iphone-data|git@github.com:iPliny/ptt-iphone-data) ;;
        *) printf 'origin 的取得與推送網址必須都是 iPliny/ptt-iphone-data；停止同步。\n'; exit 1 ;;
    esac
done
if [ "$(git -C "$PTT_DATA_DIR" branch --show-current)" != main ]; then
    printf '私人資料庫必須位於 main 分支。\n'
    exit 1
fi
working_status="$(git -C "$PTT_DATA_DIR" status --porcelain)"
if [ -n "$working_status" ]; then
    printf '私人資料庫有未提交變更，請先處理後再執行。\n'
    exit 1
fi

printf '%s 開始本機日本價格更新\n' "$(TZ=Asia/Tokyo date +%FT%T%z)"
git -C "$PTT_DATA_DIR" pull --rebase origin main
outside_paths="$(git -C "$PTT_DATA_DIR" diff --name-only origin/main...HEAD -- . ':!jp/')"
if [ -n "$outside_paths" ]; then
    printf '尚未推送的 commit 含 jp/ 以外檔案，停止同步。\n'
    exit 1
fi
"$PTT_PYTHON" -m jp.local --data "$PTT_DATA_DIR/jp"
git -C "$PTT_DATA_DIR" add -- jp/
diff_status=0
git -C "$PTT_DATA_DIR" diff --cached --quiet || diff_status=$?
if [ "$diff_status" -eq 1 ]; then
    git -C "$PTT_DATA_DIR" commit -m "本機日本價格更新 $(TZ=Asia/Tokyo date '+%Y-%m-%d %H:%M:%S %z')"
elif [ "$diff_status" -ne 0 ]; then
    exit "$diff_status"
fi
# 即使本輪無變動，仍推送上次已提交但尚未成功送出的更新。
for attempt in 0 1 2 3; do
    if git -C "$PTT_DATA_DIR" push origin HEAD:main; then
        printf '%s 同步完成\n' "$(TZ=Asia/Tokyo date +%FT%T%z)"
        exit 0
    fi
    if [ "$attempt" -eq 3 ]; then
        printf '推送失敗，已重試 3 次；保留本機 commit。\n'
        exit 1
    fi
    git -C "$PTT_DATA_DIR" pull --rebase origin main
done
