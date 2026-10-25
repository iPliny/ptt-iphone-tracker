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
- 2026-10-18：新增 `data/extract_retry.csv`（`source_url,first_failed,last_failed,attempts,last_error`，以 source_url 為鍵，整檔覆寫）。萃取暫時失敗的新文章每輪獨立加入佇列，不受 `--days` 限制；成功萃取（單支、多品項或略過）、404 後移除，首次失敗滿 `RETRY_DAYS`（14）天改記 `listings.csv` 的「略過」後移除。不改 `listings.csv` 欄位；此檔由排程產生，程式 PR 不帶資料檔。
- 2026-10-18：tracker 在 Actions 完成存檔與彙整後，把健康結果寫到 `$RUNNER_TEMP/track-health.txt` 與 `$GITHUB_STEP_SUMMARY`；workflow 完成異常價報表、資料 commit／部署觸發後才檢查。看板首頁失敗、有佇列卻沒有 200／404、Claude 帳號／權限／金鑰／額度錯誤，或一般錯誤超過 `HEALTH_ERROR_LIMIT`（10）時讓 job 失敗。`--report-only`、`--migrate` 不產生結果，本機不因此回傳非 0。
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
  - `--reparse` 的排除只限新規則明確判定是配件或一篇賣多支（`not_single_iphone`），單純抓不到售價不排除。曾被排除、之後規則又認得的文章，reparse 時依 `events.csv` 最後一筆 `排除誤判` 恢復原狀態並記 `恢復誤排除`（M.1790515861 一例）。
  - `split_blocks` 只有型號欄重複才切成新的一段；其他欄位重複（兩個 [規格]）接在原欄位後面。
  - 2026-10-15（POYU 指出 17 Pro Max 被污染）：當時把發文超過 90 天仍在售的 v1 匯入舊文（2026-03）改成略過，這些列維持略過。2026-10-18 起滿 90 天改成「逾期未售」（見下方），不再改略過。容量未知的舊列每次由 `backfill_storage` 用標題補容量（有補就存檔）；`parse_storage` 允許單位後直接接中文（「2TB銀色」）。
  - 2026-10-18：標題寫了兩支以上 iPhone（`multi_phone_title`：兩個 iPhone／Air、兩個容量、斜線分隔的型號、「兩支」「各一」）也算一篇多支，`rule_extract` 不給型號，舊列由 `drop_misparsed` 以「一篇多支」改略過。
  - 2026-10-22：型號欄第一行是 Apple Watch、AirPods、iPad、Mac 等其他產品且沒寫 iPhone（`sells_other_product`，沿用 iPhone 舊文改賣別的、標題沒改）時 `rule_extract` 不給型號；已在統計內的列本文被這樣改過時記「排除誤判」改成略過，不記改價（M.1792475735 一例）。

### 2026-10-06 一篇賣多支（只算刊登價）
- POYU 選擇：一篇賣多樣商品的文章，拆出每支 iPhone 只算進刊登數與刊登價，不算售出（無法判斷是哪一支賣掉）。
- 文章本身在 `listings.csv` 仍是「略過」；拆出的 iPhone 寫在新檔 `data/multi_items.csv`（`extract_items`，欄位 `source_url,item_no,post_time,title,model,storage,全新未拆封機,battery_health,price,first_seen`，以 source_url＋item_no 為鍵，整檔覆寫）。只在第一次解析或 `--reparse` 時更新，之後改價不追蹤。
- 支援編號清單（1. 2.／1、）、一行一支且售價逐行對應、售價用 / 分隔、每支各貼一段範本；售價只看該項第一行，非 iPhone 品項與找不到單獨售價的品項略過。
- `market_summary.csv` 最後一欄新增 `多品項刊登數`；`刊登數`、價格欄含這些 iPhone，`售出率` 只用單支刊登計算（全部是多品項時為空白）。網站的型號統計（`models`、`model_totals`）多一個 `multi` 欄並納入價格；文章列表、每日統計、事件與週報不含它們。

### 2026-10-18 逾期未售、售出誤判與沿用舊文（專案審視，POYU 選「再加 90 天規則」）
- 新狀態「逾期未售」（`STATUS_EXPIRED`）：發文滿 `STALE_DAYS`（90）天仍在售／交易中的列由 `expire_stale` 改成逾期未售並記「狀態變更」事件，之後不再回訪。計入 `market_summary.csv` 的刊登數、價格與售出率分母；網站算刊登與價格，不算在架、不算售出，在架期間到發文日＋90 天（`build_site.gone_day`）。
- 回訪排程 `revisit_urls`：`--track-days`（45）內的在售文章每次都回訪；45～90 天的距上次檢查超過 `SLOW_REVISIT_HOURS`（20）小時才回訪，約每天一次。
- `detect_status` 先剔除說明賣的原因（「換新機故售出」「因換手機，故售出」「便宜售出」）；「售出不退／售出概不退換」不算售出；以冒號結尾的「藍(已售)：」是其中一支的標籤，不算整篇售出。已售出的列改回在售時清掉 `sold_detected_at`、`days_to_sell`、`days_to_sell_basis`。
- 本文被編輯後型號改變（或已知容量改變）＝沿用舊文改賣另一支：`events.csv` 記「型號變更」（`舊型號 容量 $舊價 → 新型號 容量 $新價`），不記價格變動，`first_price` 改成新價格；網站的行情走勢從最後一次型號變更那天起才算這篇。之前已記成價格變動的舊事件不改寫。
- 頁面標頭被賣家刪掉時，標題依序用本文前幾行的「標題:」、看板列表的標題、上次的標題，不再存成空白；發信站也被刪時，本文去掉「※ 編輯／文章網址」系統行。

### 2026-09-29 改價時間
- `listings.csv` 最後追加 `last_edit_at`、`price_checked_at`，均為帶 `+08:00` 的 ISO 8601 時間。前者是本次頁面最新編輯時間，後者是最近成功確認價格的時間；缺欄舊檔可直接讀取。
- 價格有變才建立改價事件，使用「發現當下最新的編輯時間」推估。時間須不晚於抓取、不早於發文，且晚於上次成功確認價格；舊列缺少帶時區的檢查時間時不猜測舊主機時區。沒有有效編輯時間則採本次偵測時間。
- `events.csv` 保持四欄及只追加不改寫，`time` 仍是原格式的系統偵測時間。新 `data/price_event_times.csv` 同樣只追加，欄位為 `time,source_url,detail,occurred_at,detected_at,time_basis`；前三欄連結原事件，後三欄保存改價時間、偵測時間（均為帶時區的 ISO 8601）及 `ptt_edit`／`detected` 依據。由排程自然產生，程式 PR 不帶此資料檔。
- 價格不變而新增編輯紀錄時，只更新文章資訊，不新增改價事件、不覆寫任何歷史改價時間，也不據此推定交易中。萃取失敗保留上次價格、hash 與確認時間供下次重試。
- 網站將新改價時間統一轉台灣時間，用於顯示、排序及每日統計；提示保留完整秒數、時間依據與偵測時間。舊事件／缺快照的事件標示「發現改價」，不拿文章目前的編輯時間回填。其他既有時間欄位的語意維持原樣。

### 2026-09-29 時區
- CSV 裡不帶時區的時間（`post_time`、`first_seen`、`last_checked`、`sold_detected_at`、`events.csv` 的 `time` 等）一律是台灣時間。`tracker.py` 開頭強制 `TZ=Asia/Taipei`，workflow 也設了 `TZ`。
- 在這之前 Actions 主機是 UTC：PR #10 合併前寫入的這些時間都比台灣時間慢 8 小時。POYU 決定不回頭修正舊資料（2026-09-29），所以舊列的 `post_time` 仍是 UTC；發文時間在切換前的文章，之後算出的售出天數，以及舊的用編輯時間推估的售出天數，都會多算約 0.3 天。

### 2026-10-07 顏色預覽
- `listings.csv` 最後一欄新增 `color`（接在 `price_checked_at` 後）。`tracker.py` 的 `COLOR_TABLE` 保存 Apple 台灣正式色名與各代別名，來源見 `docs/colors.md`。依序看 [顏色]、[規格]／[容量]、[型號] 第一行、標題，不掃整篇本文；排除配件顏色，多色／多機／不符色盤留空。本文重解析時只有非空顏色覆寫舊值。
- `backfill_colors` 只用既存標題補在售／交易中／已售出／已刪除的空白值，不抓文章、不寫事件；`--report-only` 也會跑。
- 網站在異常價格排除後計算 `colors`，僅單支文章；多品項維持既有流程。每篇價格除以同型號×容量×全新或二手組的中位數（基準至少 3 篇），各顏色取比值中位數減 1，再四捨五入至整數百分比；各容量及全部容量各一組。某顏色可計比值的 `samples` 不足 3，價格中位數與相對值皆 null。未標顏色但有價格的文章仍可作為基準。
- 首頁和機型文章共用 `site/common.js:itemHtml`，顏色 chip 在該處統一維護。機型顏色表依容量切換，價格均為刊登價，價格中位數欄只算二手機（避免全新比例拉高某色），全部容量分頁不顯示價格欄；各色相對值相同時顯示「沒有明顯差異」，不寫並列最低；已售只是賣家狀態，非真實成交價。

### 2026-10-07 首頁最近一週預覽
- 首頁「最近一週」以資料最新一天為結尾，往前共 7 天的滾動區間，不同於週報的週日～週六；可前後移動 7 天，資料不足時顯示實際起訖與天數。
- 新刊登、售出、刪文、改價加總期間內每日計數，在架取期末值；與前 7 天比較（在架比前期末），前期不足 7 天留白。全部在前端由 `days` 計算，`data.json` 與建置流程不變；期間純函式放 `site/common.js`。

### 2026-10-07 日本買取價（第一階段）
- `jp/buyback.py` 是獨立爬蟲，只追 mobile-mix、イオシス、アメモバ的 iPhone 18 Pro／Pro Max，2026-10-09 起加上 iPhone 17、Air、17 Pro、17 Pro Max（POYU 指示；17e 不收）。イオシス、アメモバ每個機型一頁，網址與機型對照在 `IOSYS_PAGES`／`AMEMOBA_PAGES`，每頁只收該頁機型的列（アメモバ 17 Pro 頁曾混入 Air 列）；`海外版SIMフリー` 不算 SIMフリー，不收。不得混入 PTT 資料、修改 `tracker.py` 或既有台灣 CSV。新增店家請新增純 HTML parser 並在 `collect` 登錄。
- `.github/workflows/jp.yml` 每天排程三次（UTC `17 0,6,12 * * *`；約日本 09:17／15:17／21:17，避開整點以降低延遲與漏跑風險，但不保證準時；延遲的抓取照常執行），只在 main 寫入 `data/jp/` 並觸發 `pages.yml`。分支驗收只准 `--dry-run`；程式 PR 不帶任何 `data/` 檔案，第一次正式資料由合併後排程產生。GitHub schedule 會延遲或漏跑，實際抓取時間以 `runs.csv` 為準。
- 日本時間欄位均為 `Asia/Tokyo`、含 `+09:00` 的 ISO 8601，不改程序全域 `TZ`。`shop_updated` 是店家頁面更新日 `YYYY-MM-DD`，未標示留空。
- `data/jp/prices.csv` 只附加：`shop,model,storage,condition,carrier,color,price_jpy,observed_at,shop_updated,source_url`。前六欄是鍵；同價不附加，首次觀測、改價、恢復收購才新增，空白 `price_jpy` 表示下架／不收。`observed_at` 是發現該變動的時間，非店家實際改價時間。
- `data/jp/latest.csv` 整檔覆寫：`shop,model,storage,condition,carrier,color,price_jpy,since,last_checked,shop_updated,source_url`。只保留目前有價格的鍵；`since` 是目前價格第一次被觀測的時間、同價保留，`last_checked` 每次成功更新。價格是整數日圓；`color` 空白表示主價，mobile-mix 可收的精確色價另列。`condition` 為 `未開封`／`中古上限`；`carrier` 為 `SIMフリー`／`docomo`／`au`／`SoftBank`／`Rakuten`。
- `data/jp/runs.csv` 只附加：`run_at,shop,status,rows,error`，每次每家一列；`status` 為 `ok`／`fetch_error`／`parse_error`，`rows` 是本次解析筆數（失敗時可能是已解析的部分），`error` 說明原因。任一頁抓取／解析失敗、0 筆、或筆數比上次減少至少一半，都保留該店舊價格；其他店照常。
- 依序經 `fetch` 用 curl_cffi 抓取，所有請求含重試至少間隔 5 秒；イオシス同站至少 60 秒。每次失敗最多重試一次。pastec／駿河屋因擋雲端 IP 暫不做，不用代理或繞過驗證。
- `site/jp_build.py` 只讀日本 CSV，供 `build_site.py` 增加獨立建置步驟；缺檔仍輸出資料準備中的頁面。`site/jp/` 第一階段只顯示未開封・SIMフリー，價格異常保守隱藏，原始 CSV 仍保留供下載。台灣頁除頁首入口連結外不改行為。
- 驗收／回復方式見 `docs/jp-buyback-validation.md`；fixture 來源見 `tests/fixtures/jp/README.md`。離線測試使用暫存目錄，不連網、不寫專案資料。

### 2026-10-08 日本買取頁日文版
- POYU 要日文版、中文版照留：`site/jp/index.html`（中文，`jp/`）與 `site/jp/ja/index.html`（日文，`jp/ja/`）共用 `site/jp/jp.js`，介面字串在 `I18N`（zh／ja），依 `<html lang>` 切換；日文頁 `<body data-base="../">` 讓它讀 `jp/data.json`。兩頁互設 hreflang、頁首互相切換，sitemap 都列入。改頁面文字時兩個 HTML 與 `I18N` 一起改。
- 2026-10-09 POYU 要在比較表上方加「快報」（日文「速報」）：`jp.js` 的 `flash` 取 `runs.csv` 最後一次成功抓取的時間，從當次的未開封・SIMフリー主價改價中各挑漲最多、跌最多一筆（首次觀測、色價、異常價不算），全部在前端計算，`data.json` 不變。最新成功抓取沒有可計主價改價時，回溯最近 7 天內有改價的成功抓取，並標示最新與採用的兩個時間。最近變動預設顯示 10 筆，更多按鈕可展開全部或收起。

- 2026-10-18 POYU 同意加「未開封／中古」切換：頁首按鈕切換整頁（快報、比較表、走勢、最近變動）用 `未開封` 或 `中古上限`，`jp.js` 的 `setCondition` 控制 `mainRow`／`publicRow`；中古網址為 `?c=used`。整份資料沒有該狀態的店（mobile-mix 只收未開封）在比較表顯示「不收中古」。說明文字中的狀態名用 `data-cond-label`，只在某狀態顯示的用 `data-cond-only`。電信版本仍不顯示。

- 2026-10-18 POYU 要日本頁做 SEO：`site/jp_pages.py` 在建置時輸出各機型靜態頁 `jp/<slug>/`（中文）與 `jp/ja/<slug>/`（日文），標題帶年月，並列未開封與中古的主價比較表（不含色價），互設 hreflang、列入 sitemap。主頁的 `<!--JP_MODEL_LINKS-->` 換成機型連結，`#comparison` 先放 18 Pro 未開封比較表，JavaScript 載入後接手；主頁支援 `?m=<機型>` 預選機型。異常價判斷 `visible_prices` 與 `jp.js` 的 `visiblePrices` 相同，改一邊要改另一邊；介面文字在 `TEXT`，與 `I18N` 一起改。

### 2026-10-11 Claude 萃取（規則抓不到時）
- `--extractor` 預設 `auto`：環境有 `ANTHROPIC_API_KEY` 時為 `claude`，否則 `rules`，本機與沒設 secret 的行為不變。`track.yml` 從 repo secret `ANTHROPIC_API_KEY` 帶入。
- `claude` 模式先跑 `rule_extract`，結果可用就照用；規則抓不到、且 `not_single_iphone` 不成立（不是配件文、不是一篇賣多支）時，才由 `claude_extract` 呼叫 `CLAUDE_MODEL`（`claude-haiku-5-5`，effort low），用 `CLAUDE_SCHEMA` JSON schema 限定輸出，再經 `build_fields` 同一套檢查。顏色仍由 `parse_color` 從標題判斷。Claude 失敗只記錯誤、文章留到下次。
- `listings.csv` 最後一欄新增 `extractor`（`rules`／`claude`／`ollama`），空白＝加此欄前的舊列。網站不使用此欄。
- 測試以 `claude_extract` 替身執行，不連網、不需要金鑰。
- 2026-10-18 POYU 決定暫不付費：`track.yml` 固定 `--extractor rules`、不帶入 `ANTHROPIC_API_KEY`（secret 保留）。程式仍支援 claude 模式，恢復時改回 `--extractor auto` 並在該步驟加回 env。

### 2026-10-12 Blogger 週報轉貼
- POYU 的「iPhone二手週報」由 ChatGPT 排程寫好、Email 投稿到 Blogger（https://tcssh.blogspot.com/）。`site/blog.py` 讀公開 feed（標籤「週報」＋「iPhone」、標題以「iPhone二手週報」開頭），每篇存成 `data/blog/<台灣時間發布日>.json`；Blogger 上改過就覆寫，feed 範圍內消失（轉草稿／刪除）就移除。`.github/workflows/blog.yml` 每天 UTC 12:30 執行並觸發部署；`--feed <檔案>` 可改讀 Blogger 匯出檔，不刪舊檔。
- 網站 `weekly/`（列表）與 `weekly/<發布日>/`（全文轉貼）。各篇 canonical 指向 Blogger 原文，sitemap 只列 `weekly/`。內文只留 p、h2、strong、a 等排版標籤，指向本站（含舊 github.io）的連結改成站內相對路徑。
- 和 `column/`（每週日自動產生的統計週報）是兩個系列，互相連結。
- 2026-10-12 POYU 決定週報改在本站原創發布（SEO 為主），由 Claude 每週日排程撰寫，規格見 `docs/weekly-writing.md`。`python site/blog.py --publish 草稿.json` 檢查後寫入 `data/weekly/<出刊日>.json`；這些文章 canonical 指向本站並列入 sitemap。同一天兩邊都有時以 `data/weekly/` 為準。發稿 PR 只帶 `data/weekly/` 的那一個檔，POYU 看過稿並同意後才合併。

## 開發規則
- 修改後必須跑 `python -m unittest`，測試不需網路也不需 Ollama（`fetch`、`llm_extract` 皆被替換成假的）。
- 改動售出判斷（`detect_status`）或規則萃取（`rule_extract`、`is_brand_new`）時，把觸發問題的實際文章本文精簡後加進 `tests/test_tracker.py` 當回歸測試。
- 抓取必須經過 `fetch`（curl_cffi 模擬瀏覽器）；雲端 IP 用一般 requests 會被 Cloudflare 擋。
- 不要在程式裡加入任何 API key。
- 對 PTT 的請求要保留 `polite_sleep` 間隔，不要平行抓取。
- 開發用的沙箱環境通常連不到 ptt.cc；GitHub Actions 可以。請以離線測試驗證，需要看真實頁面時用 Actions。
- `data/` 裡的 CSV 由排程產生並自動 commit，不要手動編輯；改程式的 PR 不要帶 `data/` 的變動，以免和排程衝突。
- 改動走 branch + PR，不直接推 main。

### 2026-10-11 網址搬到 macshop.crawlsnek.com
- GitHub Pages 接上自訂網域 `macshop.crawlsnek.com`（Cloudflare CNAME → ipliny.github.io，DNS only），舊的 github.io 網址由 GitHub 自動轉址。`SITE_URL` 與 `jp/` 頁的 canonical／hreflang 都用新網域。
- 所有頁面頁尾有「由 CrawlSnek 提供」連到 https://crawlsnek.com/ 。
- `build_site.py` 由 `SITE_URL` 產生 robots.txt、sitemap 並代換 HTML 的 `{{SITE_URL}}`；首頁／prices 有靜態 canonical，機型頁由 `model.js` 以 `URLSearchParams` 產生只含 `m` 的 canonical，站內連結保持相對路徑。
- Search Console 新增 `https://macshop.crawlsnek.com/` 網址前置字元資源，優先用原有內嵌 GA 官方碼驗證，必要時才加 HTML 標記；提交新 sitemap、保留舊資源，不對 github.io 子路徑使用網址變更工具。

### 2026-10-16 機型頁預先產生 HTML
- `site/model_pages.py` 在建置時輸出 `models/<機型 slug>.html`，包含各機型的 title、description、canonical、主標題、公開統計、容量表與前 10 筆單支文章；只用 `build_data` 已排除異常值的資料，不改 CSV 或資料語意。
- 2026-10-25（專案審視 M8）前端 JSON 拆檔：`build_data` 仍是建置端完整資料（機型頁、行情總覽、sitemap 都讀它），寫檔時才瘦身。首頁讀 `data.json`（`home_payload`：無 trends、colors、apple、summary、model_totals，事件只留改價與刪文），機型頁讀 `models/<slug>.json`（`model_payload`：只含該機型）。文章只輸出 `PUBLIC_LISTING_FIELDS`，`OMIT_EMPTY_FIELDS` 的欄位值為 null／空字串／false 時省略（0 保留）；前端新增用到的欄位時要一起加進清單。
- 首頁機型連結與 sitemap 改指向靜態頁。原有 `model.html?m=...&s=...` 仍可使用，容量切換維持舊格式，canonical 改指向對應靜態頁；沒有伺服器或 JavaScript 轉址。
- 靜態頁使用 `data-model` 固定機型身分，容量以 `?s=` 切換；所有容量共用不含參數的 canonical。`model.js` 共用既有互動，重用靜態 canonical，資料請求失敗時保留預產內容。
- slug 由 Python `model_path` 與 JavaScript `modelPageUrl` 同規則產生；若不同機型產生相同路徑，建置應失敗，不可默默覆蓋。重建時清除輸出目錄內自有的 `models/`，避免過期頁殘留。
- 建置維持 Python 標準函式庫，GitHub Pages workflow 不增加 Node 或瀏覽器依賴。驗證見 `docs/model-prerender-validation.md`。

### 2026-10-18 機型頁每日行情走勢
- POYU 參考 used-lab.jp 的相場推移，要機型頁顯示每日行情。`build_site.price_trends` 產生 `data.json` 的 `trends`（`start` 加每組型號×容量×全新與否的 `values`，與日期逐日對齊）：每天結束時仍在架文章的當天標價中位數。在架的認定與 `daily_series` 相同，當天標價用 `價格變動` 事件倒推；異常價格與不合理改價沿用既有排除；不知道刪文日的已刪除文章不列入。
- 從 `TREND_START`（2026-09-27，現行排程開始回訪）起算，最多 `MAX_DAYS` 天；在架少於 `TREND_MIN_ON_SHELF`（3）篇的日子留空。POYU 2026-10-18 指示不標樣本數。
- 機型頁「行情走勢」卡（算不出行情的日子以虛線連接前後兩點，POYU 2026-10-18 指示，不留斷點）：全部容量分頁每個容量一條二手線（整個機型沒有二手時改用全新），單一容量分頁畫二手與全新兩條，並附 7／30 天漲跌與目前在架價格區間（只在單一容量分頁）。`model_pages.trend_summary` 預先產生摘要，漲跌格式要與 `model.js` 的 `changeText` 一致。CSV 不變。

### 2026-10-18 二手 iPhone 行情總覽頁
- `site/market.py` 在建置時輸出 `market/index.html`（靜態、不需 JavaScript），標題帶資料月份與「每日更新」，列入 sitemap（排在首頁後），首頁與機型頁頁首有入口。算法說明與 FAQ 只寫在這頁（POYU 2026-10-18 同意，不在每頁重複），首頁型號表與機型頁行情卡的說明文字後面用「算法說明」連到 `market/#faq`。只讀 `build_data` 的 `trends` 與 `models`，不另存資料檔。
- 內容：近 N 天降價最多（有 30 天資料就用 30 天，否則 7 天）、二手行情最便宜、賣得最快（售出天數中位數，至少 `FAST_MIN`＝3 筆售出）各前 10 名，以及全部機型容量的行情一覽與 FAQ（FAQPage 結構化資料）。只列最新一天仍算得出行情的機型容量；漲跌格式共用 `model_pages.trend_pct`／`pct_text`。

### 2026-10-18 分享預覽與 sitemap 日期
- 所有公開頁的分享標籤統一使用 `site/seo.py:social_meta`（靜態模板保留 `{{SITE_URL}}` 佔位符），共用 `site/og.png`（1200×630、100KB 以內）；中文 `zh_TW`、日文 `ja_JP`，Twitter 使用 `summary_large_image`。`og:url` 與 canonical 一致；舊 `model.html?m=` 由 `model.js` 同步設定兩者。GA 官方碼保留。
- `sitemap_lastmods` 只採來源日期並轉台灣時間：首頁／market 為每日統計與最近回訪的最新日期；機型頁為該機型公開文章的發文、回訪與公開事件時間最大值（多品項也含公開品項的發文日）；prices 為 `official-prices.json:updated_at`；專欄為 `generated_at` 出刊日；週報為 `published`／`updated` 較晚者，列表取各篇最新值；日本頁為 `latest.csv:last_checked` 最新日期。無可靠日期就省略 lastmod，不用建置日或檔案 mtime。
- sitemap 只列與該頁 canonical 相同的網址；`column/` 保留頁面但不列入，僅收各期。Blogger 轉貼各篇仍指向原文且不列入本站 sitemap；少量樣本的機型頁收錄規則不變。

### 2026-10-23 日本買取頁來源時間
- 日本買取主頁的最近確認時間由 `jp_pages.checked_at` 在建置時寫入 HTML，JSON 讀取失敗仍保留快照與其時間。來源必須帶時區，顯示時轉日本時間；不以建置時鐘補未知值。
- 各機型頁標題年月、摘要的確認時間與 sitemap `lastmod` 只採該機型資料，不借用其他機型的更新時間。可見時間使用日本時間；sitemap 沿用全站台灣日期規則。

### 2026-10-24 新增 iPhone Duo
- 正式名稱 `iPhone Duo`，容量 256GB／512GB／1TB／2TB；台灣色名星光白色、夜空色。別名接受 Duo、愛鳳 duo、摺疊／折疊 iPhone、iPhone Fold，含大小寫與全形；僅標題或型號欄明確指出才採用，排除 Galaxy／Pixel／Surface。
- 機型排序視為第 18 代，排在同代 Pro Max 前；slug 為 `models/iphone-duo.html`，沿用有資料才建頁的規則。
- 日本收 mobile-mix、イオシス、アメモバ；後兩家只收 Duo 專頁的 Duo 列，海外版 SIMフリー 不收。mobile-mix 顏色保存店家原文スターホワイト／ナイトスカイ（星光白／夜空）。`I18N`／`TEXT` 的通用機型文字直接使用 iPhone Duo，中日名稱相同。
- 官方購買頁、色名來源見 `docs/colors.md`；未修改其他機型價格與資料 CSV。
