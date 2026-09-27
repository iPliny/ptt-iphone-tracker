# AGENTS.md

給 Codex、Claude 等 coding agent 的專案說明。回覆與文件請用繁體中文。

## 專案目的
追蹤 PTT MacShop 版 iPhone 二手機的刊登與成交，估算各型號行情與售出速度。

## 結構
- `tracker.py`：唯一的主程式，四個階段依序執行
  1. `scan_board`：往回翻看板頁，收集 `--days` 天內標題含 `[販售]` 與 iPhone 的文章
  2. `process_article`：新文章或本文被編輯時呼叫 `llm_extract`（本機 Ollama `qwen2.5:32b`）萃取欄位
  3. 同一個 `process_article` 也負責回訪：`detect_status` 只用關鍵字判斷 在售／交易中／已售出，404 記為已刪除
  4. `build_summary`：輸出 `data/market_summary.csv`
- `data/listings.csv`：以 `source_url` 為主鍵，一篇一列；`events.csv` 只附加不改寫
- `legacy/`：v1 程式，只供參考，不要修改

## 開發規則
- 修改後必須跑 `python -m unittest`，測試不需網路也不需 Ollama（`fetch`、`llm_extract` 皆被替換成假的）。
- 改動售出判斷（`detect_status`、`SOLD_TITLE_KW`、`_SOLD_LINE_RE`）時，一併在 `tests/test_tracker.py` 加正反例，避免版規文字被誤判。
- 不要在程式裡加入任何 API key；LLM 萃取只走本機 Ollama。
- 對 PTT 的請求要保留 `polite_sleep` 間隔，不要平行抓取。
- CI／雲端環境通常連不到 ptt.cc，無法做真實抓取；請以離線測試驗證。
- `data/` 裡的 CSV 由程式產生，不要手動編輯內容。
- 改動走 branch + PR，不直接推 main。
