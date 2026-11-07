#!/bin/bash
# 只安裝與重新載入排程，不立即執行爬蟲。
set -euo pipefail
umask 077
CODE_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
source "$CODE_DIR/local/bootstrap.sh"
if [ "$#" -gt 1 ]; then printf '用法：bash local/install.sh [BASE絕對路徑]\n' >&2; exit 1; fi
if [ "$#" -eq 1 ]; then BASE="$1"; else read_base; fi
allowed_path "$BASE" || { printf 'BASE 不可位於 TCC 目錄或使用相對路徑\n' >&2; exit 1; }
valid_base "$BASE" || { log "BASE 必須包含兩個有效 clone：$BASE" >&2; exit 1; }
domain="gui/$(id -u)"
# 不中斷正在執行的 launchd job；使用者稍後再安裝。
state="$(launchctl print "$domain/com.crawlsnek.ptt-local-crawler" 2>/dev/null || true)"
if printf '%s\n' "$state" | /usr/bin/grep -Eq 'state = running|pid = [0-9]+'; then
    log '爬蟲正在執行，請等結束後再安裝。' >&2; exit 1
fi
# 手動啟動的 runner 也使用此檔案鎖。
exec 9< "$BASE/ptt-iphone-tracker/jp/local_lock.py"
# flock 綁定共用的 open-file description；shell 保留 fd 9 到安裝結束。
"$(find_python)" - <<'PYLOCK'
import fcntl
import sys
try:
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    sys.exit("爬蟲正在執行，請等結束後再安裝。")
PYLOCK
save_base
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cp "$CODE_DIR/local/bootstrap.sh" "$CONFIG_DIR/ptt-bootstrap.sh"
chmod 700 "$CONFIG_DIR/ptt-bootstrap.sh"
"$(find_python)" - "$CODE_DIR" <<'PY'
import plistlib
import sys
from pathlib import Path
home = Path.home()
source = Path(sys.argv[1]) / 'local/com.crawlsnek.ptt-local-crawler.plist'
values = {'__HOME__': str(home), '__BOOTSTRAP__': str(home / 'Library/Application Support/crawlsnek/ptt-bootstrap.sh')}
def fill(value):
    if isinstance(value, str):
        for key, replacement in values.items():
            value = value.replace(key, replacement)
        return value
    if isinstance(value, list):
        return [fill(item) for item in value]
    if isinstance(value, dict):
        return {key: fill(item) for key, item in value.items()}
    return value
target = home / 'Library/LaunchAgents/com.crawlsnek.ptt-local-crawler.plist'
target.write_bytes(plistlib.dumps(fill(plistlib.loads(source.read_bytes()))))
PY
plist="$HOME/Library/LaunchAgents/com.crawlsnek.ptt-local-crawler.plist"
plutil -lint "$plist"
domain="gui/$(id -u)"
if launchctl print "$domain/com.crawlsnek.ptt-local-crawler" >/dev/null 2>&1; then
    launchctl bootout "$domain/com.crawlsnek.ptt-local-crawler"
fi
loaded=0
for attempt in 1 2 3 4; do
    if launchctl bootstrap "$domain" "$plist"; then loaded=1; break; fi
    log "bootstrap 失敗（第 $attempt 次），等待重試"
    sleep 2
done
[ "$loaded" = 1 ] || { log '嚴重錯誤：排程重新載入失敗' >&2; exit 1; }
printf '已重新載入排程；BASE=%s\n' "$BASE"
