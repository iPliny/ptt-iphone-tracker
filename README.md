# PTT MacShop iPhone 二手機成交追蹤

網站：[PTT MacShop交易觀測](https://macshop.crawlsnek.com/)。

## 版權與授權

Copyright © 2026 iPliny。本專案未提供對外的開源或開放資料授權；作者保留自行商用及另行授權原創成果的權利。第三方內容與事實資料的使用範圍，見 [版權與使用範圍](COPYRIGHT.md)。

每 6 小時由 GitHub Actions 自動掃描 PTT MacShop 版的 iPhone 販售文，回訪還在賣的文章判斷是否已售出，結果 commit 回 `data/`。不需要開電腦。

## 怎麼運作
1. **掃描**：往回翻看板，收集 `--days` 天內標題含 `[販售]` 與 iPhone 的文章。
2. **萃取**：新文章（或本文被編輯的文章）依 MacShop 發文範本（`[型號]`、`[規格]`、`[保固]`、`[售價]`…）用規則抓出型號、容量、價格、電池、保固、是否全新未拆。一篇賣多支、只賣配件的文章會被略過。賣家沒照範本寫、規則抓不到的文章，若有設定 `ANTHROPIC_API_KEY`，改請 Claude（Haiku）萃取，`listings.csv` 的 `extractor` 欄會記為 `claude`。
3. **回訪**：45 天內仍在售的文章每次逐篇重新打開，45～90 天的約每天一次；標題或本文出現「已售出」就記為已售出並算出售出天數；文章被刪記為已刪除；滿 90 天還沒賣掉記為逾期未售（仍算刊登與價格，不算在架）。
4. **彙整**：輸出各型號 × 容量的行情。

ptt.cc 前面有 Cloudflare，雲端主機用一般 `requests` 會拿到 403，所以抓取改用 `curl_cffi` 模擬瀏覽器。

## 資料
```
data/listings.csv        每篇文章一列的最新狀態（主鍵 source_url）
data/events.csv          變動紀錄：新刊登、價格變動、狀態變更
data/extract_retry.csv   萃取暫時失敗的網址與重試紀錄，首次失敗滿 14 天改記略過
data/market_summary.csv  各型號 × 容量：刊登數、售出率、刊登價／已售標價中位數、售出天數中位數
data/macshop_raw_data_v1.csv  v1 原始資料（已匯入 listings.csv）
```
`status`：在售／交易中／已售出／已刪除／略過（非單一 iPhone 或抓不到單機價格）。
`days_to_sell_basis`：售出天數怎麼來的。「觀測」是兩次檢查之間看到它賣掉；「推估」是第一次看到就已售出，用文章最後一次編輯時間（賣家通常賣掉時改標題）減發文時間；沒有編輯紀錄則為「無法推估」。

## 排程與手動執行
- Claude 萃取：在 GitHub repo 的 Settings → Secrets and variables → Actions 新增 `ANTHROPIC_API_KEY`。沒設定時排程照舊只用規則。
- 排程：`.github/workflows/track.yml`，台灣時間 02、08、14、20 點。
- 手動：GitHub 上 Actions → Track PTT listings → Run workflow，可調 `days`（往回掃幾天）與 `track_days`（回訪幾天內的文章）。

本機也能跑：
```bash
pip install -r requirements.txt
python tracker.py                      # 完整執行（規則萃取；有 ANTHROPIC_API_KEY 時規則抓不到的改問 Claude）
python tracker.py --extractor rules    # 只用規則，不呼叫 Claude
python tracker.py --extractor ollama   # 改用本機 Ollama qwen2.5:32b 萃取（需另外 pip install ollama）
python tracker.py --track-only         # 只回訪既有文章
python tracker.py --report-only        # 只重算行情
python tracker.py --reparse            # 萃取規則改過後：追蹤期內所有文章（含已售出）重新萃取欄位；Actions 手動執行時勾選 reparse
python -m unittest                     # 離線測試
```

## 限制
網站的「我的收藏」可免登入保存型號／容量或文章篩選條件；只存在目前瀏覽器，不跨裝置同步，清除網站資料後會消失。收藏使用每次開啟時載入的資料，不保存舊價格，也不發送通知。設計與審閱說明見 [第一版免登入收藏](docs/no-login-watchlist.md)。

- PTT 沒有真實成交價，「成交價」是售出時最後的標價。
- 賣家直接刪文記為「已刪除」，不算進售出數。
- 售出天數的精準度約等於排程間隔（6 小時）；兩次檢查間隔超過 3 天就不計天數。
- 規則萃取依發文範本，賣家亂寫格式時可能抓不到而被略過（沒有設定 Claude 金鑰時）；遇到時把文章網址丟進 issue，補一條測試再修規則。

`legacy/master_pipeline_v1.py` 是原本的 v1 程式，留作參考。

## 程式與私人資料拆分（準備中）

目前仍使用私人程式庫與 Cloudflare Git 建置。此分支提出改為公開程式庫＋私人資料庫，尚未切換；請先讀 [切換步驟與停止點](docs/data-repo-split.md)，不要直接合併。

切換後資料庫根目錄保存原 `data/` 的全部內容。本機在沒有 `data/` 的乾淨程式 checkout 中執行：

```bash
gh repo clone iPliny/ptt-iphone-data data
python site/build_site.py --out _site
```

已有舊 `data/` 時先備份並核對，不要覆蓋。日後資料變更在 `data/` 內 commit/push，程式變更在外層走 PR。原創週報改向私人資料庫的 `weekly/` 提交 PR。

Actions 所需 secrets：`DATA_REPO_TOKEN`（只授權私人資料庫 Contents read/write、Metadata read）、`CLOUDFLARE_API_TOKEN`（指定帳戶 Cloudflare Pages Edit）、`CLOUDFLARE_ACCOUNT_ID`。切換驗收完成後才移除舊 `CLOUDFLARE_PAGES_DEPLOY_HOOK`。

網站仍使用公開行情 JSON；原始 CSV、內部抓取紀錄不得上傳網站或公開 Actions artifact。CI 不讀私人資料、不使用上述 secrets。
