# iPhone二手週報：每週寫稿與發布規格

POYU 2026-10-12 決定：週報只發在本站（https://macshop.crawlsnek.com/weekly/），目的是從 Google 搜尋帶流量。由 Claude 每週日排程撰寫並發布，取代原本 ChatGPT＋Blogger 的流程。本檔是排程每次執行時要讀的完整規格；POYU 當次的明確要求優先。

## 一、時程與期間
- 排程在週日日本時間 21:17 啟動，晚於 `column.yml`（21:00）產生的 `data/column/<週日>.json`。
- 本期＝剛結束的週日～週六（台灣時間），和統計週報同一期。檔名與網址用**本期結束後的週日**（出刊日），例如 10/11–10/17 這期是 `2026-10-18`。
- `data/weekly/<出刊日>.json` 已存在就不重寫（除非 POYU 要求修改）；`data/blog/` 也有同期文章時照常發，網站以本站版本為準。
- 期別：接續既有編號（#1～#3 在 Blogger，`data/blog/`；之後看 `data/weekly/` 最大號 +1）。

## 二、資料
- 取最新 main，記下完整 commit SHA，整篇只用這個 commit 的資料。
- 主數字以 `data/column/<本期週日>.json` 為準（和網站統計週報一致），需要更細的切法再回 `data/listings.csv`、`events.csv`、`price_event_times.csv`、`multi_items.csv` 依同樣期間與排除規則重算。欄位與時間口徑見 `AGENTS.md`。
- 遵守網站的排除規則：異常價格、不合理改價、配件、一篇賣多支（只算刊登價）都照 `build_site.py` 的處理，不自己放寬。
- 證據紀律：刊登價、已售出文章的最後標價都不是實際成交價；推文「私」不是私訊總數；刪文不是售出；推估售出時間不是成交時間；改價後售出不能寫成「因為降價所以成交」；少量樣本不寫成行情。新機上市、官方售價等背景只引用 Apple 等原始來源，或 `site/apple_prices.json`／`site/official-prices.json`。

## 三、文風
- 先載入 `pyl-blog-weekly-writing` skill（iPhone 校準範例、證據層級、A／G 段）照著寫；skill 讀不到就不發布，回報原因。
- 台灣繁體中文，正文約 2000 字（1700–2300），情報與專欄各半；每主題只留 1–3 個關鍵數字；開頭 150–250 字帶本週具體現象；3–5 個主題由資料決定；結尾回到機況、預算、議價等取捨。
- 不用爆跌、神價、必買等標題黨字眼；不虛構親身交易經歷。

## 四、SEO
- 標題：`iPhone二手週報#<期別>：<本期核心型號或現象>（YYYY/M/D）`，自然含台灣讀者會搜的型號詞（例如「iPhone 17 Pro 二手價」）。
- `description`（搜尋說明）150 字以內，建議 60–120 字，概括本文並帶核心型號，不寫成交價。
- `labels` 恰好 5 個：「iPhone」「二手市場」「週報」＋2 個本文有實質討論的搜尋詞（優先核心型號＋意圖，如「iPhone 17 Pro」「iPhone二手價格」）。
- 小標用 h2（必要時 h3），寫成讀者會問的問題或有張力的短句。
- 內部連結至少三個，連結文字要說清楚能做什麼：首頁 `https://macshop.crawlsnek.com/`、機型頁 `https://macshop.crawlsnek.com/model.html?m=iPhone%2017%20Pro`（型號名稱 URL 編碼）、本期統計週報 `https://macshop.crawlsnek.com/column/<本期週日>/`。建置時會自動改成站內相對路徑。
- 可用標籤：p、h2、h3、strong、em、a、small、ul、ol、li、table 系列、blockquote；其他會被清掉。文末用 `<small>` 寫資料說明：期間、樣本數、排除規則、固定 commit 的資料連結（`https://github.com/iPliny/ptt-iphone-tracker/tree/<SHA>/data`）。

## 五、審稿與發布（POYU 2026-10-12：要先看過才上線）
1. 草稿寫成 JSON：`{"id": "<出刊日>", "title", "description", "labels": [5 個], "html", "period": "YYYY/M/D–M/D", "commit": "<SHA>"}`。
2. `python site/blog.py --publish 草稿.json`：檢查欄位、字數、至少一個站內連結，清理後寫入 `data/weekly/<出刊日>.json`。有錯就修稿再跑。
3. `python site/build_site.py --out /tmp/site` 確認 `weekly/<出刊日>/index.html` 產生、canonical 指向本站，再跑 `python -m unittest`。
4. 開分支、commit 只含 `data/weekly/<出刊日>.json`，開 PR，**不要合併**。
5. 把建好的文章頁存成 `/mnt/project-files/weekly/<出刊日>.html`，`style.css` 內嵌進 `<head>`，讓檔案可單獨開啟預覽，在專案 thread 回報：期別、標題、資料期間、5 個 labels、搜尋說明、PR 連結，附上預覽檔，請 POYU 看稿。
6. POYU 給回饋就改稿，重跑步驟 2–3，推到同一個 PR 並更新預覽檔；改寫時保留 POYU 指定的說法。
7. POYU 明確說可以上線後，CI 綠燈才合併，確認 `pages.yml` 部署成功，回報文章網址。
8. 卡住時說明卡在資料、文風或部署哪一層，不要發半成品。
