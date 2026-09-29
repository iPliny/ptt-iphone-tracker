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

## 開發規則
- 修改後必須跑 `python -m unittest`，測試不需網路也不需 Ollama（`fetch`、`llm_extract` 皆被替換成假的）。
- 改動售出判斷（`detect_status`）或規則萃取（`rule_extract`、`is_brand_new`）時，把觸發問題的實際文章本文精簡後加進 `tests/test_tracker.py` 當回歸測試。
- 抓取必須經過 `fetch`（curl_cffi 模擬瀏覽器）；雲端 IP 用一般 requests 會被 Cloudflare 擋。
- 不要在程式裡加入任何 API key。
- 對 PTT 的請求要保留 `polite_sleep` 間隔，不要平行抓取。
- 開發用的沙箱環境通常連不到 ptt.cc；GitHub Actions 可以。請以離線測試驗證，需要看真實頁面時用 Actions。
- `data/` 裡的 CSV 由排程產生並自動 commit，不要手動編輯；改程式的 PR 不要帶 `data/` 的變動，以免和排程衝突。
- 改動走 branch + PR，不直接推 main。
