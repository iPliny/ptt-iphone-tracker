# iPhone 二手機成交追蹤 v2

## 這版改了什麼
| 問題（v1） | v2 做法 |
|---|---|
| 只看最新 2 頁，文章被擠下去就不再回訪，所以永遠抓不到「已售出」（現有 11 筆全是「否」） | 每次執行都把 45 天內仍在售的文章逐篇重新打開，只用關鍵字判斷售出／交易中／已刪除，不耗 LLM |
| CSV 是附加寫入，同一篇被編輯會出現兩列 | `listings.csv` 每篇一列、保存最新狀態；變動另記在 `events.csv`（新刊登、改價、售出、刪文） |
| 雜湊包含推文，有人推文就重跑 LLM | 只對「本文」算雜湊，推文不觸發重新解析 |
| 固定翻 2 頁 | 翻到 `--days` 天前為止（預設 3 天，上限 30 頁） |
| 型號寫法不一（iphone 11 pro / iPhone 17 pro max） | 統一成 `iPhone 11 Pro`、`iPhone 15 Pro Max`，也吃 `15pm`、`i14` 等縮寫 |
| 內文任何「售出」都算已售 | 只認標題、或本文中單獨一行的「已售出」；「售出後…」這類版規句不算 |
| 沒有彙整 | `market_summary.csv`：各型號×容量的刊登數、售出率、刊登價／已售標價中位數、售出天數中位數 |

LLM 萃取提示詞與 v1 相同，另外把標題也一併送進去。

## 檔案結構
```
tracker.py               主程式（掃描 → LLM 萃取 → 回訪追蹤 → 行情彙整）
data/listings.csv        每篇文章一列的最新狀態
data/events.csv          變動紀錄（新刊登、改價、售出、刪文；第一次執行後產生）
data/market_summary.csv  各型號 × 容量行情
data/macshop_raw_data_v1.csv  v1 原始資料（已匯入 listings.csv）
legacy/master_pipeline_v1.py  v1 程式，保留參考
tests/                   離線測試（假 PTT 頁面 + 假 LLM）
```

## 執行
```bash
pip install -r requirements.txt

# 一次性：3 月那 11 篇超過 45 天追蹤期，手動放寬回訪一次看賣掉沒
python tracker.py --no-llm --track-days 400

# 之後每天跑（需開 Ollama，模型 qwen2.5:32b）
python tracker.py

# 測試
python -m unittest
```

售出天數的精準度取決於你多久跑一次；兩次檢查間隔超過 3 天就不計算天數（只記錄已售出）。
建議每天固定跑，例如 `crontab -e` 加一行（路徑改成你的）：
```
0 */6 * * * cd ~/ptt-iphone-tracker && /usr/bin/python3 tracker.py >> run.log 2>&1
```

## 限制
- PTT 沒有真實成交價，「成交價」是售出時最後的標價。
- 賣家若直接刪文，記為「已刪除」，不算進售出數。
- v1 的 `scraping_history.json` 已不再使用（雜湊改存在 listings.csv）。
