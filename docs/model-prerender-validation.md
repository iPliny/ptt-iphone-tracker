# 機型頁預產 HTML 驗收

原本各機型都從 `model.html?m=...` 取得相同的 HTML，標題、canonical、行情與文章必須等 JavaScript 執行後產生。新建置由 `site/model_pages.py` 為每個公開機型產生可直接閱讀的 HTML，再由原有 `model.js` 更新資料及提供互動。

## 網址與相容性

| 入口 | 行為與 canonical |
| --- | --- |
| `models/iphone-18-pro.html` | 靜態標準頁；原始 HTML 已有此機型內容 |
| `models/iphone-18-pro.html?s=256GB` | 同頁容量切換；canonical 不含容量 |
| `model.html?m=iPhone+18+Pro&s=256GB` | 舊書籤照常使用，不轉址；canonical 指向靜態標準頁 |

首頁新連結與 sitemap 指向靜態標準頁。靜態頁的機型由 HTML 的 `data-model` 決定，附加其他 `m` 參數不會改變頁面身分。既有收藏仍以機型與容量為鍵，沒有新增儲存格式。

GitHub Pages 不會依查詢參數回傳不同原始 HTML，所以保留舊網址作相容入口；舊入口仍需 JavaScript。爬蟲從 sitemap 或新連結取得的新靜態頁，不必等 JavaScript 就能讀取摘要與容量表。

## 內容與建置

- 每個機型的預產內容包含專屬 title、description、唯一 canonical、h1、更新時間、四張統計卡、容量表、Apple 原廠資訊及前 10 筆單支文章。
- 只讀既有公開資料；統計沿用 `build_data` 的異常價格排除結果，多品項仍僅納入刊登與刊登價。售出價仍是賣家售出時最後標價，非實際成交價。
- JavaScript 接手後仍提供圖表、顏色比較、容量切換、狀態篩選、價格排序、更多文章及收藏。資料請求失敗時，靜態頁保留建置時內容並顯示提示。
- 不新增前端框架、套件或部署服務。原 Pages workflow 仍執行 `python site/build_site.py --out _site`。
- 建置會重建自有 `models/` 目錄並檢查路徑重複，避免過期頁殘留或不同機型互相覆蓋。

## 自動驗證

在專案根目錄執行：

```sh
python -m unittest
node --test tests/*.test.cjs
python site/build_site.py --out _site
git diff --check
git diff --name-only -- data/
```

Python 測試涵蓋原始 HTML 可直接閱讀、不同機型不混資料、HTML 跳脫、來源連結協定、未知價格不顯示零元、原廠來源、多品項語意、slug 衝突與過期頁清除。Node 測試涵蓋新舊路由、canonical 與 sitemap 對齊、容量與追蹤參數排除、重用既有 canonical、篩選、排序、更多、收藏相容與請求失敗時保留靜態內容。

## 2026-10-16 本機驗收

以 `7061ee1` 的公開資料建置：1,016 篇單支文章、36 個機型靜態頁。產物與 `data/` 不納入此程式 PR。

完整 Python 測試 166 項與 Node 測試 65 項通過。另將同一份輸入交給修改前後的 `build_data` 比對，確認資料結構及各值相同，發布 CSV 位元組也完全相同。逐頁檢查 36 個原始 HTML 的標題、主標題、canonical、可見主內容與相對腳本資產，並核對 sitemap；結果見 `model-prerender-validation/build-checks.json`。

內建瀏覽器檢查新靜態頁及舊查詢入口：

- 256GB／512GB 容量切換更新內容與網址，canonical 始終只有一個且指向不含容量的靜態頁。
- 已售出篩選為 10 篇，價格由高到低；更多文章由 10 篇展開到 20 篇。
- 鍵盤空白鍵可收藏；切到舊入口及重新載入後，同機型同容量的收藏能還原。
- 1280px 桌面及 375px、320px 手機檢查；手機沒有頁面橫向溢出。
- 結構化瀏覽器紀錄見 `model-prerender-validation/`；截圖只放在 PR 說明，不納入 repo。

## 合併後與回復

此 PR 未合併、未部署，未送出索引或 sitemap 請求。合併後，正常部署會產生新靜態頁並更新 sitemap；Google 的標準網址選擇及收錄仍需後續檢索，不保證立即收錄或排名提升。

若需回復，撤銷此 PR 的程式變更並依原 workflow 重建部署，即回到舊查詢入口及 sitemap；既有資料與收藏不需轉換。
