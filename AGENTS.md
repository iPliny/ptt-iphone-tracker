# AGENTS.md

給 Codex、Claude 等 coding agent 的專案說明。回覆與文件請用繁體中文。

## 專案目的
追蹤 PTT MacShop 版 iPhone 二手機的刊登與成交，估算各型號行情與售出速度。

## 結構
- `tracker.py`：唯一的主程式，四個階段依序執行
  1. `scan_board`：往回翻看板頁，收集 `--days` 天內標題含 `[販售]` 與 iPhone 的文章
  2. `process_article`：新文章或本文被編輯時萃取欄位；預設 `rule_extract`（依發文範本的規則），`--extractor ollama` 才走本機 LLM
  3. 同一個 `process_article` 也負責回訪：`detect_status` 只用關鍵字判斷 在售／交易中／已售出，404 記為已刪除
  4. `build_summary`：輸出 `data/market_summary.csv`
- `data/listings.csv`：以 `source_url` 為主鍵，一篇一列；`events.csv` 只附加不改寫
- `.github/workflows/track.yml`：每 6 小時在 GitHub Actions 執行，把 `data/` commit 回 main 後觸發 `pages.yml` 重新部署網站；`ci.yml` 跑測試
- `data/` 的 CSV 欄位是網站的介面，改欄位名稱或意義時要在這裡註明並同步改網站
  - 2026-09-27 新增 `listings.csv` 的 `days_to_sell_basis`（觀測／推估／無法推估）與 `market_summary.csv` 的 `售出天數樣本(觀測/推估)`，都加在最後一欄。推估＝第一次看到就已售出時，用文末最後一筆「※ 編輯」時間減發文時間
  - 2026-09-29：`listings.csv` 新增 `private_msg_count`，加在最後一欄（`days_to_sell_basis` 之後）。正常回訪時只更新在售／交易中文章；排除原 PO、移除私密／私人／隱私／自私／私下／私心／公私／勿私／不私／別私／不要私後，含「私」「站內」「密你」「已密」的推文按 ID 去重計人數，推／噓／→ 都算。空白＝未計算、0＝已計算但無人私訊；售出或刪除後保留最後值，網站不顯示。
- `legacy/`：v1 程式，只供參考，不要修改
- 每週專欄「二手 iPhone 行情週報」（2026-10-04）：`site/column.py` 為上一個完整週（週日～週六，台灣時間）算統計，存成 `data/column/<週日日期>.json`，每期只產生一次，之後資料變動不改舊期數字；`.github/workflows/column.yml` 每週日 UTC 12:00（日本 21:00／台灣 20:00）執行並觸發部署。內文 1000 字以內（`MAX_CHARS`，POYU 2026-10-04 指定），建置時由 `article()` 依統計套範本產生，改範本會一起改到舊期文字。頁面是靜態 HTML：`column/` 顯示最新一期全文（canonical 指向該期），`column/<週日日期>/` 為各期固定網址，都列入 sitemap.xml，`<head>` 要保留 GA 官方碼。

### 2026-10-05 機型頁的 Apple 原廠資訊
- 機型頁顯示「Apple 原廠」區塊，資料是 `site/apple_prices.json`（人工查詢，`build_site.apple_prices` 轉成 `data.json` 的 `apple`）。POYU 指定：官網還在賣的放購買連結與現行官網價（`on_sale`，附 `checked_at`）；停售機型放停售前最後的官方建議售價（`discontinued`，附來源），不放上市價。
- 新機上市、官網調價或機型下架時要手動更新：下架的機型從 `on_sale` 移到 `discontinued`，價格用下架前的官網價。查不到的容量填 null，網站顯示「查無官方價格」。

### 2026-10-06 歷代官方價格頁
- `site/prices.html`（資料 `site/official-prices.json`，說明見 `docs/official-prices.md`）列 iPhone 歷代台灣上市價、後續容量／調價與初代美國價。POYU 2026-10-06 同意上線。只有 Apple 原文（A）與電信官方（B）有金額，其他查核狀態一律 `null`，未核實金額不得出現在任何公開檔案。
- 現行官網價／停售前最終價仍只放 `site/apple_prices.json`（機型頁），兩者不重複存。

### 2026-10-05 異常價格不公開
- POYU 指示明顯怪的價格「優先不要 po」。`parse_price` 先移除日期（如 AppleCare+ 到 2028/1/22），避免把年份當售價。
- 網站與週報再加一層：`build_site.drop_price_outliers` 把和同型號×容量×全新與否中位數（不到 5 筆改用同型號）相比低於一半或高於兩倍的價格改成不公開；`implausible_price_change` 把降幅超過一半或漲幅超過一倍的改價事件排除。CSV 原始資料不改。被隱藏的價格與改價由 track.yml 每次寫進 `data/price_outliers.csv`（`build_site.py --outlier-report`，整檔覆寫，不放上網站），POYU 要「不發但手上記著」。

### 2026-10-06 配件與誤判機型
- 標題有殼、保護貼等配件字樣又找不到容量的文章視為賣配件，`rule_extract` 不給型號（例：「iphone 17 pro max 原廠織紋殼」$1,200）。標題提到殼但有容量的仍是手機（「17Pro Max 原廠透明殼」256G $34,000）。
- 型號欄只寫「iPhone18」、標題寫「18 pro」這類同一代缺字尾的情況，以標題的完整型號為準。
- 每次執行最後 `drop_misparsed` 會把舊規則留下、現在看得出是誤判的列（配件、`iPhone X Pro` 這類不存在的型號）改成「略過」，並在 `events.csv` 記一筆 `排除誤判`；`--reparse` 時本文沒改、新規則判定不是單支 iPhone 的列也同樣處理。網站與週報只顯示仍在統計內文章的事件。

### 2026-09-29 改價時間
- `listings.csv` 最後追加 `last_edit_at`、`price_checked_at`，均為帶 `+08:00` 的 ISO 8601 時間。前者是本次頁面最新編輯時間，後者是最近成功確認價格的時間；缺欄舊檔可直接讀取。
- 價格有變才建立改價事件，使用「發現當下最新的編輯時間」推估。時間須不晚於抓取、不早於發文，且晚於上次成功確認價格；舊列缺少帶時區的檢查時間時不猜測舊主機時區。沒有有效編輯時間則採本次偵測時間。
- `events.csv` 保持四欄及只追加不改寫，`time` 仍是原格式的系統偵測時間。新 `data/price_event_times.csv` 同樣只追加，欄位為 `time,source_url,detail,occurred_at,detected_at,time_basis`；前三欄連結原事件，後三欄保存改價時間、偵測時間（均為帶時區的 ISO 8601）及 `ptt_edit`／`detected` 依據。由排程自然產生，程式 PR 不帶此資料檔。
- 價格不變而新增編輯紀錄時，只更新文章資訊，不新增改價事件、不覆寫任何歷史改價時間，也不據此推定交易中。萃取失敗保留上次價格、hash 與確認時間供下次重試。
- 網站將新改價時間統一轉台灣時間，用於顯示、排序及每日統計；提示保留完整秒數、時間依據與偵測時間。舊事件／缺快照的事件標示「發現改價」，不拿文章目前的編輯時間回填。其他既有時間欄位的語意維持原樣。

### 2026-09-29 時區
- CSV 裡不帶時區的時間（`post_time`、`first_seen`、`last_checked`、`sold_detected_at`、`events.csv` 的 `time` 等）一律是台灣時間。`tracker.py` 開頭強制 `TZ=Asia/Taipei`，workflow 也設了 `TZ`。
- 在這之前 Actions 主機是 UTC：PR #10 合併前寫入的這些時間都比台灣時間慢 8 小時。POYU 決定不回頭修正舊資料（2026-09-29），所以舊列的 `post_time` 仍是 UTC；發文時間在切換前的文章，之後算出的售出天數，以及舊的用編輯時間推估的售出天數，都會多算約 0.3 天。

## 開發規則
- 修改後必須跑 `python -m unittest`，測試不需網路也不需 Ollama（`fetch`、`llm_extract` 皆被替換成假的）。
- 改動售出判斷（`detect_status`）或規則萃取（`rule_extract`、`is_brand_new`）時，把觸發問題的實際文章本文精簡後加進 `tests/test_tracker.py` 當回歸測試。
- 抓取必須經過 `fetch`（curl_cffi 模擬瀏覽器）；雲端 IP 用一般 requests 會被 Cloudflare 擋。
- 不要在程式裡加入任何 API key。
- 對 PTT 的請求要保留 `polite_sleep` 間隔，不要平行抓取。
- 開發用的沙箱環境通常連不到 ptt.cc；GitHub Actions 可以。請以離線測試驗證，需要看真實頁面時用 Actions。
- `data/` 裡的 CSV 由排程產生並自動 commit，不要手動編輯；改程式的 PR 不要帶 `data/` 的變動，以免和排程衝突。
- 改動走 branch + PR，不直接推 main。
