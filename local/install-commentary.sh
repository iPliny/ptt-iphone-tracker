#!/bin/bash
# 安裝「每月底更新價格短評」的 launchd 排程（每天 22:00 Mac 系統時區執行，非月底自動略過）。
set -euo pipefail
CODE_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
LABEL=com.crawlsnek.ptt-price-commentary
TARGET="$HOME/Library/LaunchAgents/$LABEL.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
sed -e "s#__CODE_DIR__#$CODE_DIR#g" -e "s#__HOME__#$HOME#g" "$CODE_DIR/local/$LABEL.plist" > "$TARGET"
plutil -lint "$TARGET"
domain="gui/$(id -u)"
launchctl print "$domain/$LABEL" >/dev/null 2>&1 && launchctl bootout "$domain/$LABEL"
launchctl bootstrap "$domain" "$TARGET"
echo "已安裝 $LABEL；程式位置 $CODE_DIR（請讓這份 clone 保持在 main）"
