# PTT MacShop iPhone 二手機成交追蹤

每 6 小時由 GitHub Actions 自動掃描 PTT MacShop 版的 iPhone 販售文，回訪還在賣的文章判斷是否已售出，結果 commit 回 `data/`。不需要開電腦。

## 怎麼運作
1. **掃描**：往回翻看板，收集 `--days` 天內標題含 `[販售]` 與 iPhone 的文章。
2. **萃取**：新文章（或本文被編輯的文章）依 MacShop 發文範本（`[型號]`、`[規格]`、`[保固]`、`[售價]`…）用規則抓出型號、容量、價格、電池、保固、是否全新未拆。一篇賣多支、只賣配件的文章會被略過。
3. **回訪**：45 天內仍在售的文章逐篇重新打開，標題或本文出現「已售出」就記為已售出並算出售出天數；文章被刪記為已刪除。
4. **彙整**：輸出各型號 × 容量的行情。

ptt.cc 前面有 Cloudflare，雲端主機用一般 `requests` 會拿到 403，所以抓取改用 `curl_cffi` 模擬瀏覽器。

## 資料
```
data/listings.csv        每篇文章一列的最新狀態（主鍵 source_url）
data/events.csv          變動紀錄：新刊登、價格變動、狀態變更
data/market_summary.csv  各型號 × 容量：刊登數、售出率、刊登價／已售標價中位數、售出天數中位數
data/macshop_raw_data_v1.csv  v1 原始資料（已匯入 listings.csv）
```
`status`：在售／交易中／已售出／已刪除／略過（非單一 iPhone 或抓不到單機價格）。
`days_to_sell_basis`：售出天數怎麼來的。「觀測」是兩次檢查之間看到它賣掉；「推估」是第一次看到就已售出，用文章最後一次編輯時間（賣家通常賣掉時改標題）減發文時間；沒有編輯紀錄則為「無法推估」。

## 排程與手動執行
- 排程：`.github/workflows/track.yml`，台灣時間 02、08、14、20 點。
- 手動：GitHub 上 Actions → Track PTT listings → Run workflow，可調 `days`（往回掃幾天）與 `track_days`（回訪幾天內的文章）。

本機也能跑：
```bash
pip install -r requirements.txt
python tracker.py                      # 完整執行（規則萃取）
python tracker.py --extractor ollama   # 改用本機 Ollama qwen2.5:32b 萃取（需另外 pip install ollama）
python tracker.py --track-only         # 只回訪既有文章
python tracker.py --report-only        # 只重算行情
python tracker.py --reparse            # 萃取規則改過後：追蹤期內所有文章（含已售出）重新萃取欄位；Actions 手動執行時勾選 reparse
python -m unittest                     # 離線測試
```

## 限制
- PTT 沒有真實成交價，「成交價」是售出時最後的標價。
- 賣家直接刪文記為「已刪除」，不算進售出數。
- 售出天數的精準度約等於排程間隔（6 小時）；兩次檢查間隔超過 3 天就不計天數。
- 規則萃取依發文範本，賣家亂寫格式時可能抓不到而被略過；遇到時把文章網址丟進 issue，補一條測試再修規則。

`legacy/master_pipeline_v1.py` 是原本的 v1 程式，留作參考。
