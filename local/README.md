# 本機日本價格爬蟲

`run.sh` 在家用 Mac 執行，使用私人資料庫 `iPliny/ptt-iphone-data` 的獨立 clone。來源、欄位與機況對照見 [本機爬蟲說明](../docs/local-crawler.md)。買取資料寫入私人資料庫的 `jp/`，販賣資料寫入 `jp/sell/`；不觸發網站部署。

先確認 Python 已安裝專案 `requirements.txt` 既有套件，並已透過本機 Git 登入私人資料庫。腳本使用 `PTT_PYTHON` 指定的 Python；未設定時優先使用程式庫 `.venv/bin/python`，再找 `python3`。`PTT_DATA_DIR` 預設為 `$HOME/Documents/Codex/dispatch/ptt-iphone-data`。

單獨檢查解析與抓取（不寫資料、不進行 Git 同步）：

```sh
cd "$HOME/Documents/Codex/dispatch/ptt-iphone-tracker"
python -m jp.local --data "$HOME/Documents/Codex/dispatch/ptt-iphone-data/jp" --dry-run
python -m jp.local --data "$HOME/Documents/Codex/dispatch/ptt-iphone-data/jp" --only pastec,iosys-sell --dry-run
```

正式手動執行會寫入、提交並推送私人資料庫：

```sh
PTT_PYTHON="$HOME/Documents/Codex/dispatch/ptt-iphone-tracker/.venv/bin/python" \
PTT_DATA_DIR="$HOME/Documents/Codex/dispatch/ptt-iphone-data" \
/bin/bash "$HOME/Documents/Codex/dispatch/ptt-iphone-tracker/local/run.sh"
```

腳本確認獨立 clone、取得與推送的 origin 都是指定資料庫、分支為 `main`，且工作目錄及 index 都乾淨，再 `git pull --rebase origin main`。若本機尚未推送的 commit 含 `jp/` 以外檔案，也會停止。抓取成功後只 `git add -- jp/`，有變動才以「本機日本價格更新 <日本時間>」提交，再推送；第一次推送失敗後最多重試 3 次，每次先 rebase，衝突即停。所有輸出追加至 `~/Library/Logs/ptt-local-crawler.log`。

整段 Git 同步與直接執行 `jp.local` 共用 `fcntl.flock` 鎖；鎖住既存 `jp/local_lock.py`，不建立鎖檔，程序結束即釋放。重疊執行會回傳非 0。請固定使用同一份程式庫 checkout，不要在執行途中更換此檔案或另開 clone 排程。

任何步驟失敗即停止並回傳非 0；抓取失敗可能留下 `runs.csv` 或其他成功店家的更新，請檢查私人 CSV 與 log，先自行處理未提交變更再重跑。push 全數失敗則保留本機 commit，下次乾淨執行會再次推送。腳本不自動 reset、丟棄變更或解決 rebase 衝突。

## 安裝 launchd

目前只提供範本，尚未安裝。`StartCalendarInterval` 使用 **Mac 系統時區**，請在系統設定將時區設為 `Asia/Tokyo`，才能每天日本時間 09:40、21:40 執行。plist 的 `TZ` 僅控制子程序，不會改變 launchd 的排程時區。這是登入使用者的 LaunchAgent；睡眠、關機或未登入會影響實際啟動時間。

確認 Python 路徑後，以 `plistlib` 填入絕對路徑（支援路徑中的空白與 XML 特殊字元），然後安裝：

```sh
cd "$HOME/Documents/Codex/dispatch/ptt-iphone-tracker"
export PTT_PYTHON="$PWD/.venv/bin/python"
export PTT_DATA_DIR="$HOME/Documents/Codex/dispatch/ptt-iphone-data"
"$PTT_PYTHON" - <<'PY'
import os
from pathlib import Path
import plistlib

root = Path.cwd().resolve()
home = Path.home()
values = {
    "__CODE_DIR__": str(root),
    "__DATA_DIR__": str(Path(os.environ["PTT_DATA_DIR"]).expanduser().resolve()),
    "__PYTHON__": str(Path(os.environ["PTT_PYTHON"]).expanduser().absolute()),
    "__HOME__": str(home),
}
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

template = root / "local/com.crawlsnek.ptt-local-crawler.plist"
target = home / "Library/LaunchAgents/com.crawlsnek.ptt-local-crawler.plist"
target.parent.mkdir(parents=True, exist_ok=True)
(home / "Library/Logs").mkdir(parents=True, exist_ok=True)
target.write_bytes(plistlib.dumps(fill(plistlib.loads(template.read_bytes()))))
print(target)
PY
plutil -lint "$HOME/Library/LaunchAgents/com.crawlsnek.ptt-local-crawler.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.crawlsnek.ptt-local-crawler.plist"
launchctl print "gui/$(id -u)/com.crawlsnek.ptt-local-crawler"
```

如需立即執行（會提交並推送私人資料）：

```sh
launchctl kickstart "gui/$(id -u)/com.crawlsnek.ptt-local-crawler"
```

## 解除安裝

```sh
launchctl bootout "gui/$(id -u)/com.crawlsnek.ptt-local-crawler"
rm "$HOME/Library/LaunchAgents/com.crawlsnek.ptt-local-crawler.plist"
```

解除安裝保留私人資料、Git commits 與 log。改排程或路徑時，先 bootout，重新產生 plist，再 bootstrap。
