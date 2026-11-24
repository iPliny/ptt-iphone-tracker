#!/bin/bash
# 安裝「每月底更新價格短評」的 launchd 排程（每天 22:00 Mac 系統時區執行，非月底自動略過）。
# 排程用專用的程式 clone（RUNNER），不受平常開發分支切換影響；每次執行前會 git pull --ff-only。
set -euo pipefail
LABEL=com.crawlsnek.ptt-price-commentary
RUNNER="${PTT_COMMENTARY_RUNNER:-$HOME/Documents/Codex/dispatch/ptt-iphone-tracker-runner}"
PY="${PTT_PYTHON:-/opt/homebrew/bin/python3}"
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
if [ ! -d "$RUNNER/.git" ]; then
    mkdir -p "$(dirname "$RUNNER")"
    git clone https://github.com/iPliny/ptt-iphone-tracker.git "$RUNNER"
fi
git -C "$RUNNER" checkout main
git -C "$RUNNER" pull --ff-only
[ -x "$RUNNER/.venv/bin/python" ] || "$PY" -m venv "$RUNNER/.venv"
"$RUNNER/.venv/bin/pip" install -q -r "$RUNNER/requirements.txt"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
sed -e "s#__CODE_DIR__#$RUNNER#g" -e "s#__PYTHON__#$RUNNER/.venv/bin/python#g" -e "s#__HOME__#$HOME#g" \
    "$RUNNER/local/$LABEL.plist" > "$TARGET"
plutil -lint "$TARGET"
domain="gui/$(id -u)"
launchctl print "$domain/$LABEL" >/dev/null 2>&1 && launchctl bootout "$domain/$LABEL"
launchctl bootstrap "$domain" "$TARGET"
echo "已安裝 $LABEL；程式 clone：$RUNNER"
