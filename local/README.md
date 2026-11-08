# 本機日本價格爬蟲

`run.sh` 在家用 Mac 執行，使用私人資料庫 `iPliny/ptt-iphone-data` 的獨立 clone。來源、欄位與機況對照見 [本機爬蟲說明](../docs/local-crawler.md)。買取資料寫入私人資料庫的 `jp/local/`，販賣資料寫入 `jp/sell/`；不觸發網站部署。

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

腳本確認獨立 clone、取得與推送的 origin 都是指定資料庫、分支為 `main`，工作目錄若只有白名單 runs.csv 追加的失敗紀錄會先提交，其他未提交變更停止，再 fetch 並 rebase `origin/main`。若本機尚未推送的 commit 含 `jp/` 以外檔案，也會停止。抓取完成後（含失敗）只 `git add -- jp/`，有變動才以「本機日本價格更新 <日本時間>」提交，再推送；第一次推送失敗後最多重試 3 次，每次先 rebase，只有 runs.csv 的純追加衝突自動合併去重，其餘衝突中止本次 rebase 並停止。所有輸出追加至 `~/Library/Logs/ptt-local-crawler.log`。

固定鎖檔預設為 `$HOME/Library/Application Support/crawlsnek/ptt-local-crawler.lock`，可用 `PTT_LOCAL_LOCK_PATH` 覆寫；資料夾權限 700、鎖檔 600，鎖檔不刪除。bootstrap 在任何 pull、venv、pip 前由系統 `/usr/bin/perl` 取得非阻塞 flock，透過 `PTT_LOCAL_LOCK_FD` 將 fd 傳給 exec 的 run.sh 與 Python，一路持鎖到結束。CLI、手動 runner 與 install 共用此鎖，繼承時核對 dev/inode 與持鎖狀態；重疊執行非 0 結束。dry-run 不取鎖、不建立鎖檔。

抓取失敗仍提交並推送失敗紀錄與成功店家的更新，同步成功後回傳爬蟲原本的非 0。push 全數失敗則保留本機 commit，下次乾淨執行會再次推送。腳本不 reset、不 force push、不丟棄別人的資料。啟動時若已有 rebase／merge，自動 abort 回原分支並記錄 log 後繼續，abort 失敗才停止；cherry-pick／revert 仍須人工處理。

## 安裝 launchd

`StartCalendarInterval` 使用 **Mac 系統時區**，請在系統設定將時區設為 `Asia/Tokyo`，才能每天日本時間 09:40、21:40 執行。plist 的 `TZ` 僅控制子程序，不會改變 launchd 的排程時區。這是登入使用者的 LaunchAgent；睡眠、關機或未登入會影響實際啟動時間。

先確保 `/opt/homebrew/bin/python3` 可用、本機 Git 可讀取兩個 repo 並推送私人資料庫。從含本次更新的程式庫執行：

```sh
/bin/bash local/install.sh "$HOME/ai-cowork/ptt-local-crawler"
```

安裝可重複執行：寫入 `~/Library/Application Support/crawlsnek/ptt-local-crawler.conf`（純文字 `BASE=/絕對路徑`，空白不加引號），把 bootstrap 複製到同目錄的 `ptt-bootstrap.sh`，產生 `~/Library/LaunchAgents/com.crawlsnek.ptt-local-crawler.plist`，bootout 舊服務後 bootstrap 載入。不立即執行爬蟲；log 仍是 `~/Library/Logs/ptt-local-crawler.log`。未傳參數時沿用 conf，沒有 conf 則預設 `~/ai-cowork/ptt-local-crawler`。

plist 只呼叫固定位置的 bootstrap，不依賴 repo 位置或 WorkingDirectory。每次啟動先讀 conf，核對 BASE 下 `ptt-iphone-tracker`、`ptt-iphone-data` 兩個獨立 clone 的 fetch／push origin。找不到有效 BASE 時搜尋 HOME 深度 5 內的資料 clone（BASE 名稱不限），核對兩個 origin；所有有效候選記 log，選資料庫最近 commit 時間最新者，同時間依路徑排序。不分大小寫排除 `~/Library`、`~/.Trash`、`~/Documents`、`~/Desktop`、`~/Downloads` 與指向它們的符號連結。

沒有 conf，或 conf 明確標記 `BASE_EXISTED=0` 且 BASE 不存在又沒有候選時才 clone；舊 conf 視為曾安裝，找不到候選即大聲報錯、非 0 結束，不建立替代資料庫。成功後 conf 寫入 `BASE_EXISTED=1`；既存錯誤 clone 不覆寫。程式庫每輪先 `git pull --ff-only`，失敗記 log 後沿用現有版本。缺少 `.venv` 時依下述 Python 順序建立，首次或 requirements 更新時安裝依賴；安裝失敗下輪重試。最後以 BASE 設定 `PTT_DATA_DIR`、`PTT_PYTHON` 並 exec `run.sh`。

**不要搬動或刪除 BASE 資料夾。** 需要搬移時，先停排程並等待執行結束，再搬完整兩個 clone（含未提交資料與 `.git`），最後以新 BASE 重跑 `install.sh`，或修改 conf；避免搬到 TCC 目錄。自我搜尋是失聯時的補救，不取代正常搬移程序。bootstrap 更新後也要重跑安裝，固定位置的副本才會更新。

如需立即執行（會提交並推送私人資料）：

```sh
launchctl kickstart "gui/$(id -u)/com.crawlsnek.ptt-local-crawler"
```

## 解除安裝

```sh
launchctl bootout "gui/$(id -u)/com.crawlsnek.ptt-local-crawler"
rm "$HOME/Library/LaunchAgents/com.crawlsnek.ptt-local-crawler.plist"
```

解除安裝保留私人資料、Git commits、conf、bootstrap 與 log。改排程後重跑 `install.sh`。

## 雲端停更告警

`.github/workflows/local-crawler-watch.yml` 每兩小時（UTC 偶數小時的 31 分）讀取私人資料庫 `jp/local/runs.csv`，由 `DATA_REPO_TOKEN` checkout；以工作流程的 `issues: write` 權限管理程式庫 issue。GitHub schedule 可能延遲，14 小時是成功紀錄門檻，並非保證第 14 小時即發通知。

モバステ、イオシス任一家最後 `status=ok` 超過 14 小時，或沒有有效成功紀錄，就建立固定標題「本機爬蟲停更告警」的 issue；已有 open issue 則編輯內文更新狀態，只有停更店家集合改變時留言。兩家都恢復到 14 小時內才留言並關閉。只採含時區、非未來的成功時間，失敗不延長健康時間；紀錄須已推送才算恢復。issue 僅含店名與成功／檢查時間，不含私人 CSV 原列或錯誤內容。checkout／API 失敗會使 workflow 失敗，不誤報恢復；通知是否送達依 GitHub 個人的 watch／通知設定。

安裝前驗證兩個 clone 與 BASE，若 launchd 顯示正在執行或 runner 鎖被占用則提示並退出；安裝期間持有 runner 鎖。bootout 後 bootstrap 最多嘗試 4 次，間隔 2 秒，耗盡後非 0 結束。Python 依序尋找 `/opt/homebrew/bin/python3`、`/usr/local/bin/python3`、`/usr/bin/python3`；bootstrap 的 Git 指令限制 120 秒（clone 300 秒），pip 限制 600 秒，以 timeout 或 perl alarm 執行，兩者皆無則直接執行。測試使用暫存 HOME 與假 launchctl，不載入實際排程。
