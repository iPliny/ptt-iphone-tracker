# 本機日本價格爬蟲（2026-10-30）

`python -m jp.local --data <私人資料庫的 jp 目錄> [--dry-run] [--only pastec,iosys-sell,iosys-buyback]` 使用家用 IP，初版 parser 依 POYU 於 2026-10-30 保存的 HTML 驗收；2026-11-03 的連線查核與分流交接見下方。安裝與解除排程見 [local/README.md](../local/README.md)。

## 資料與共用邏輯

モバステ與イオシス買取寫入指定目錄的 `local/` 子目錄內的 `prices.csv`、`latest.csv`、`runs.csv`；イオシス販賣寫入其 `sell/` 子目錄的同名檔案。兩者共用 `jp.buyback` 的 `KEY`、CSV 欄位、時間格式、歷史追加與最新快照更新，販賣價不進買取 CSV。`source_url` 對モバステ是郵送買取規格頁，對イオシス販賣是該組最低價的商品頁；同價時依網址排序選擇，顏色留空。

`buyback.fetch` 新增可選的各站間隔，`validate_rows`、`apply_results` 新增可選的機況清單，原本呼叫的預設值不變。全域請求（含重試）至少相隔 5 秒；pastec.net、iosys.co.jp 各至少 10 秒；駿河屋保留 30 秒設定但沒有啟用抓取；既有 k-tai-iosys.com 仍為 60 秒。每次失敗最多重試一次，全部序列執行。

整個來源的任一頁抓取、解析或分頁失敗，該店整批保留舊價；0 筆、筆數少至少一半、衝突鍵等沿用驗證。其他來源仍可更新，失敗寫私人 `runs.csv`，CLI 回傳非 0。`--dry-run` 同樣驗證既有快照與本次筆數，但不建立資料目錄、CSV 或鎖檔。stdout 含店家、狀態、筆數與抓取失敗的 HTTP 狀態／連線錯誤類別。固定鎖檔預設為 `$HOME/Library/Application Support/crawlsnek/ptt-local-crawler.lock`，可用 `PTT_LOCAL_LOCK_PATH` 覆寫；資料夾權限 700、鎖檔 600，鎖檔不刪除。bootstrap 在任何 pull、venv、pip 前由系統 `/usr/bin/perl` 取得非阻塞 flock，透過 `PTT_LOCAL_LOCK_FD` 將 fd 傳給 exec 的 run.sh 與 Python，一路持鎖到結束。CLI、手動 runner 與 install 共用此鎖，繼承時核對 dev/inode 與持鎖狀態；重疊執行非 0 結束。dry-run 不取鎖、不建立鎖檔。

## モバステ（pastec）買取

從 `https://pastec.net/iphone` 的規格列找郵送買取連結，再讀 `?purchase_type=net` 規格頁；只收既有 `MODELS`、`STORAGES`，17e 不收，不碰 `/api/`。原始目錄含 Duo 與現有目標機型，不靠猜網址增加機型。

範例規格頁 `https://pastec.net/iphone/iphone17pro256gb?purchase_type=net` 的 `.assess__model-card-badges` **明載 SIMフリー**，因此寫入 `carrier=SIMフリー`。若是其他已知電信版本，依明示版本記錄；版本不明或海外版使該店失敗，避免推定為 SIMフリー。列表與規格頁的機型、容量必須一致。

| 頁面機況 | 儲存方式 |
|---|---|
| 新品區的「未開封」 | `未開封` |
| 中古 A／中古 B／中古 C | 取三者最高可收價格，記為 `中古上限` |
| 新品 開封済、ジャンク、不能動作的商品 | 不收 |

主價保留表列價格；範例有橘／藍色減價說明，本版不建立色價列，也不把減價說明算進主價格。未見可靠的價格更新日期時 `shop_updated` 留空，不採頁首新聞日期。裁切規格 fixture 解析為 2 筆。

## イオシス販賣

目錄 `https://iosys.co.jp/items/smartphone/iphone` 的已確認入口如下；Pro 入口同時含 Pro Max，按商品名稱區分。目錄缺少任何既有入口時整店失敗，避免將缺頁當成下架。範例沒有可確認的 Duo 販賣入口，本版未猜測或加入。

| 入口尾段 | 收錄機型 |
|---|---|
| `iphone18_pro` | iPhone 18 Pro／Pro Max |
| `iphone17_pro` | iPhone 17 Pro／Pro Max |
| `iphone_air` | iPhone Air |
| `iphone17?not=pro+17e` | iPhone 17 |

只讀 `#ajax-item-main` 的商品列，不讀推薦商品或其他版面價格。依原 HTML 的 `rel=next` 逐頁收齊，驗證同站、同機型、查詢條件不變與連續頁碼；分頁不完整、循環或超過 100 頁會失敗。完成全部頁面後，每個店家 × 機型 × 容量 × 機況 × 版本取最低刊登價，顏色不分組。

| 頁面機況 | `condition` |
|---|---|
| 未使用品 | `未使用品` |
| 中古Aランク | `中古A` |
| 中古Bランク | `中古B` |
| 中古Cランク | `中古C` |

版本從商品名稱的国内版SIMフリー、docomo／au／SoftBank／Rakuten 版識別；海外版與版本不明的商品不納入。商品名稱的 `ネットワーク利用制限▲` 仍按頁面原有 A／B／C 等級計入；現有欄位沒有獨立保存該限制，最低價可能包含此類商品，查閱時以 `source_url` 的條件為準。若後續要排除或獨立區分，需另定統計規則。

原始 17 Pro 範例首頁有 24 件、共 8 頁；此次裁切保留 7 件（含同規格重複商品、不同容量／機況／版本），聚合為 6 筆。後頁沒有提供真實 HTML，測試中的後頁屬合成變體，未宣稱完成真實全站抓取。

## 駿河屋、Back Market、手機王

駿河屋 `https://www.suruga-ya.jp/kaitori/search_buy?search_word=iPhone` 的 `suruga.html` 有 10 筆書籍／配件結果，唯一明確價格是 iPhone 13 矽膠殼的 1,100 円；其他列是 `kakaku=-1`／メールにてお見積，沒有目標 iPhone 手機報價。因此這份檔案不足以建立手機解析器，也不能據此斷言價格一定由 JavaScript 載入。本版不抓、不寫駿河屋資料。

HTML 未提供可確認的價格 JSON API 網址。後續可先保存精確機型搜尋的 HTML，並檢視檔案引用的 `/drupal/modules/surugaya_buy/assets/js/search_buy_pc.js`、`/drupal/themes/surugaya/js/ansinSearch/kaitori.js`，確認手機商品與價格實際來源；目前未取得這兩個檔案。若之後採集，仍須遵守至少 30 秒同站間隔，不繞過驗證。

Back Market 日本列表 curl 為 403，本版未做。手機王（sogi）條款禁止轉載，因此不抓。モバステ買取已納入網站日本買取頁，中古採 A〜C 最高收購價；店家狀態會標示超過 48 小時未更新。イオシス販賣仍未公開，不呈現台日價差，GitHub workflows 不變。

`local/run.sh` 抓取失敗仍提交並推送 `jp/` 的失敗紀錄，commit 訊息標明失敗；同步成功後保留爬蟲原本的非 0 結束碼，避免未提交的 runs.csv 阻塞下一輪。安全檢查及推送重試不變，離線替身測試見 `tests/test_local_runner.py`。


## 2026-11-03 停更修正與交接

イオシス七個原買取入口在本機均實測 HTTP 200，既有 parser 共解析 240 筆（40／40／30／40／20／30／40）；Actions 舊 log 只有 fetch_error，沒有 HTTP 狀態，故不能把根因斷言為 Cloudflare 403。新增的診斷會顯示 HTTP 狀態或 curl 錯誤碼／連線類別，完整 Actions 例外仍留私人 runs.csv。沒有改網址、parser 或排程，也不使用代理或繞過驗證。

本機預設新增 `iosys-buyback`，沿用 IOSYS_PAGES 與既有 60 秒間隔。買取三檔獨立放在 `jp/local/`，Actions 繼續寫 `jp/`；販賣仍在 `jp/sell/`。網站在該店第一次本機成功後採用本機快照及後續紀錄，保留之前的 Actions 歷史，排除接手後該店的 Actions 價格與狀態。首次接手用舊快照驗證筆數，保留同價 since，也能記錄下架；失敗不接手。兩邊不再同寫任何買取 CSV，無須改 Actions 排程或停用來源。

`jp.local_sync` 先 fetch 再 rebase，僅白名單 `jp/runs.csv`、`jp/local/runs.csv`、`jp/sell/runs.csv` 允許 CSV 完整列合併去重，且兩邊都必須包含共同基底的完整列集合；以兩邊列的聯集保留順序並去重，支援多個本機 commit。其他衝突中止本次 rebase、保留原 commit；啟動前殘留 rebase／merge 會先 abort 並記錄後繼續，abort 失敗才停止；只有白名單 runs.csv 追加失敗紀錄的未提交變更會自動提交，其他變更停止。失敗仍提交／推送的行為已存在於此分支，這次保留並以測試確認。

Claude 後續處理（本次未執行）：先暫停 launchd 並備份私人 checkout（含 .git、未提交變更及 rebase 現場），更新 runner 後，啟動時會自動 abort 殘留 rebase／merge 回原 commit，再提交僅追加的失敗紀錄；若有其他未提交變更，仍需人工整理。確認 main、乾淨且資料無遺失後，將本次程式更新到本機 runner；先以 `--only iosys-buyback --dry-run --data <暫存目錄>` 驗證，再正式跑一次並確認 push。網站建置端也必須套用 jp_build.py 才會讀取新子目錄。不要刪舊 jp/ CSV，不要 force push。


## 2026-11-07 路徑自我修復與雲端告警

11/04 搬移 BASE 後，舊 plist 寫死的 repo 路徑失效並 exit 78；本次改由 repo 外固定位置 `~/Library/Application Support/crawlsnek/ptt-bootstrap.sh` 啟動。`local/install.sh [BASE絕對路徑]` 冪等寫 conf、複製 bootstrap、產生 plist 並重新載入，保留 09:40／21:40（系統需為 JST）與既有 log。安裝不立即抓取。詳細命令見 [安裝說明](../local/README.md#安裝-launchd)。

bootstrap 讀同目錄 `ptt-local-crawler.conf` 的 BASE，預設 `~/ai-cowork/ptt-local-crawler`。失聯時搜尋 HOME 深度 5 內的資料 clone，BASE 名稱不限，核對兩個 clone 的 origin；多個有效候選全部記 log，選資料庫最近 commit 時間最新者（同時間依路徑排序）。不分大小寫排除 Library／.Trash／Documents／Desktop／Downloads 及指向它們的符號連結。只有沒有 conf，或明確標記 `BASE_EXISTED=0` 且 BASE 不存在又無候選時才 clone；舊 conf 一律視為曾安裝，找不到候選即大聲記 log 並非 0 結束，不另建資料庫。成功安裝或找到 BASE 後保存 `BASE_EXISTED=1`。建立 `.venv` 並安裝依賴；不覆寫既有無效 clone。每輪程式庫 pull --ff-only 失敗不阻擋舊版執行，最後以 BASE 設定兩個環境變數交給 run.sh。依賴安裝失敗仍停止並留下 log，下輪重試。

不要搬動或刪除 BASE 資料夾；要搬請先停排程、等執行結束、保留兩個完整 clone，再跑 install.sh 指定新路徑或改 conf。安裝與更新固定 bootstrap 副本都需人工執行安裝腳本。

雲端 `local-crawler-watch.yml` 每兩小時以既有 `DATA_REPO_TOKEN` 取得私人資料，檢查 `jp/local/runs.csv` 的モバステ、イオシス最後成功時間。任一家超過 14 小時（或缺少有效紀錄）建立「本機爬蟲停更告警」，已有 open 則編輯內文，只有停更店家集合改變時留言，兩家均恢復後留言關閉。權限為 contents: read、issues: write，不依賴 Mac 存活。只公開店名與成功時間，不轉貼原始列、錯誤或價格。GitHub 排程有延遲，通知須依帳戶設定；資料 checkout／API 失敗由 workflow 失敗顯示，不當成恢復。

本次只修改程式與離線測試；沒有執行 install.sh、更新實際 runner 或啟用雲端排程。部署程式後仍須安裝與觀察實際排程／成功推送才能確認運作。

安裝前驗證兩個 clone 與 BASE，若 launchd 顯示正在執行或 runner 鎖被占用則提示並退出；安裝期間持有 runner 鎖。bootout 後 bootstrap 最多嘗試 4 次，間隔 2 秒，耗盡後非 0 結束。Python 依序尋找 `/opt/homebrew/bin/python3`、`/usr/local/bin/python3`、`/usr/bin/python3`；bootstrap 的 Git 指令限制 120 秒（clone 300 秒），pip 限制 600 秒，以 timeout 或 perl alarm 執行，兩者皆無則直接執行。測試使用暫存 HOME 與假 launchctl，不載入實際排程。
