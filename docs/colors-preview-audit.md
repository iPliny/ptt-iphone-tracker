# 顏色預覽資料稽核（2026-10-07）

基準提交：`fdeb022df64b4498c827bd09f8e7eea0dbc579f1`。使用該提交的本機 data/ 執行 `python tracker.py --report-only`，再執行 `python site/build_site.py --out /tmp/site`。沒有重新抓取 PTT。以下是此快照的解析結果，不代表逐篇本文人工確認。

- 納入追蹤（在售／交易中／已售出／已刪除）：560 篇；有色 485 篇（86.6%），未標色 75 篇。
- 不含已刪除的在售／交易中／已售出：495 篇；有色 434 篇（87.7%）。
- 所有補值皆來自既存標題；下表原始寫法列出實際匹配詞（同篇多詞以「／」串接），每篇只計一次，合計 485。
- 顏色統計僅使用通過既有價格排除的文章；下列解析覆蓋率則包含被隱藏價格的文章，因為「有顏色」不代表價格可公開。

## 驗證狀態

- Python 離線測試 121 項通過；Node 離線測試 32 項通過（含完整機型頁腳本的最小 DOM 替身，驗證容量切換、並列、樣本不足、舊版資料與 HTML 跳脫）。
- 預覽成功建置；未合併、未部署。data/ 已還原，不納入 PR；events.csv 位元組未變，multi_items.csv 原先不存在且未建立。2 筆被既有規則判為異常的價格在網站資料中仍為 null。
- **待完成畫面驗收**：瀏覽器在讀取 localhost 前，因無法驗證管理員強制安全政策而拒絕存取。尚無桌機／手機、淺色／深色實際渲染截圖，也未確認真實瀏覽器的橫向溢出。離線 DOM 替身測試不等於視覺驗收。
- 待補 9 張畫面：iPhone 17 Pro Max 全部容量／256GB × 桌機／手機 × 淺色／深色 8 張；首頁帶顏色 chip 1 張。建議桌機 1280px、手機 390px，並額外檢查 320px。恢復瀏覽器後完成，再將此 PR 提交人工覆核；本 PR 不可自動合併。

## 各型號未標示顏色篇數

|型號|納入追蹤|有色|未標示顏色|
|---|---:|---:|---:|
|iPhone 11|9|8|1|
|iPhone 11 Pro|1|1|0|
|iPhone 12|7|6|1|
|iPhone 12 Pro|6|6|0|
|iPhone 12 Pro Max|3|2|1|
|iPhone 12 mini|1|1|0|
|iPhone 13|8|8|0|
|iPhone 13 Pro|15|13|2|
|iPhone 13 Pro Max|5|4|1|
|iPhone 13 mini|6|5|1|
|iPhone 14|11|9|2|
|iPhone 14 Plus|5|2|3|
|iPhone 14 Pro|19|16|3|
|iPhone 14 Pro Max|7|7|0|
|iPhone 15|4|3|1|
|iPhone 15 Plus|1|1|0|
|iPhone 15 Pro|49|44|5|
|iPhone 15 Pro Max|30|22|8|
|iPhone 16|3|3|0|
|iPhone 16 Plus|5|3|2|
|iPhone 16 Pro|48|41|7|
|iPhone 16 Pro Max|37|30|7|
|iPhone 16e|1|1|0|
|iPhone 17|30|28|2|
|iPhone 17 Pro|58|50|8|
|iPhone 17 Pro Max|55|46|9|
|iPhone 17e|3|2|1|
|iPhone 18 Pro|52|49|3|
|iPhone 18 Pro Max|71|66|5|
|iPhone 8 Plus|1|0|1|
|iPhone Air|7|7|0|
|iPhone XS|2|1|1|

## 所有實際原始寫法 → 標準名稱統計

|型號|標題實際匹配詞|標準色|篇數|
|---|---|---|---:|
|iPhone 11|白色|白色|1|
|iPhone 11|紅|(PRODUCT)RED|1|
|iPhone 11|紫色|紫色|2|
|iPhone 11|綠色|綠色|1|
|iPhone 11|黃色|黃色|2|
|iPhone 11|黑|黑色|1|
|iPhone 11 Pro|夜幕綠|夜幕綠色|1|
|iPhone 12|白|白色|1|
|iPhone 12|白色|白色|2|
|iPhone 12|紅|(PRODUCT)RED|1|
|iPhone 12|紫色|紫色|1|
|iPhone 12|黑|黑色|1|
|iPhone 12 Pro|太平洋藍|太平洋藍色|1|
|iPhone 12 Pro|石墨色|石墨色|1|
|iPhone 12 Pro|石墨／灰|石墨色|1|
|iPhone 12 Pro|藍色|太平洋藍色|2|
|iPhone 12 Pro|銀／白色|銀色|1|
|iPhone 12 Pro Max|太平洋藍|太平洋藍色|1|
|iPhone 12 Pro Max|銀|銀色|1|
|iPhone 12 mini|黑|黑色|1|
|iPhone 13|白色|星光色|2|
|iPhone 13|粉色|粉紅色|3|
|iPhone 13|紅|(PRODUCT)RED|1|
|iPhone 13|綠|綠色|1|
|iPhone 13|藍|藍色|1|
|iPhone 13 Pro|天峰藍|天峰藍色|5|
|iPhone 13 Pro|松嶺青|松嶺青色|1|
|iPhone 13 Pro|石墨色|石墨色|2|
|iPhone 13 Pro|銀|銀色|1|
|iPhone 13 Pro|銀色|銀色|1|
|iPhone 13 Pro|黑|石墨色|2|
|iPhone 13 Pro|黑色|石墨色|1|
|iPhone 13 Pro Max|石墨色|石墨色|1|
|iPhone 13 Pro Max|藍|天峰藍色|2|
|iPhone 13 Pro Max|金色|金色|1|
|iPhone 13 mini|星光色|星光色|1|
|iPhone 13 mini|白|星光色|2|
|iPhone 13 mini|黑|午夜色|2|
|iPhone 14|星光／白|星光色|2|
|iPhone 14|白色|星光色|1|
|iPhone 14|紫色|紫色|2|
|iPhone 14|藍|藍色|2|
|iPhone 14|藍色|藍色|1|
|iPhone 14|黃|黃色|1|
|iPhone 14 Plus|紫|紫色|1|
|iPhone 14 Plus|藍色|藍色|1|
|iPhone 14 Pro|紫|深紫色|4|
|iPhone 14 Pro|紫色|深紫色|6|
|iPhone 14 Pro|金|金色|1|
|iPhone 14 Pro|金色|金色|2|
|iPhone 14 Pro|黑色|太空黑色|3|
|iPhone 14 Pro Max|太空黑|太空黑色|1|
|iPhone 14 Pro Max|太空黑色|太空黑色|1|
|iPhone 14 Pro Max|白|銀色|1|
|iPhone 14 Pro Max|白色|銀色|1|
|iPhone 14 Pro Max|紫色|深紫色|1|
|iPhone 14 Pro Max|銀／白色|銀色|1|
|iPhone 14 Pro Max|黑|太空黑色|1|
|iPhone 15|粉|粉紅色|1|
|iPhone 15|粉紅色|粉紅色|1|
|iPhone 15|綠|綠色|1|
|iPhone 15 Plus|藍色|藍色|1|
|iPhone 15 Pro|原鈦|原色鈦金屬|5|
|iPhone 15 Pro|原鈦色|原色鈦金屬|10|
|iPhone 15 Pro|白色|白色鈦金屬|5|
|iPhone 15 Pro|藍|藍色鈦金屬|3|
|iPhone 15 Pro|藍色|藍色鈦金屬|3|
|iPhone 15 Pro|藍鈦|藍色鈦金屬|4|
|iPhone 15 Pro|藍鈦色|藍色鈦金屬|1|
|iPhone 15 Pro|鈦色|原色鈦金屬|1|
|iPhone 15 Pro|銀|白色鈦金屬|1|
|iPhone 15 Pro|銀色|白色鈦金屬|1|
|iPhone 15 Pro|銀／白色|白色鈦金屬|1|
|iPhone 15 Pro|黑|黑色鈦金屬|6|
|iPhone 15 Pro|黑色|黑色鈦金屬|1|
|iPhone 15 Pro|黑鈦|黑色鈦金屬|1|
|iPhone 15 Pro|黑鈦色|黑色鈦金屬|1|
|iPhone 15 Pro Max|原色|原色鈦金屬|1|
|iPhone 15 Pro Max|原色鈦|原色鈦金屬|1|
|iPhone 15 Pro Max|原色鈦金|原色鈦金屬|1|
|iPhone 15 Pro Max|原鈦|原色鈦金屬|3|
|iPhone 15 Pro Max|原鈦色|原色鈦金屬|3|
|iPhone 15 Pro Max|白|白色鈦金屬|2|
|iPhone 15 Pro Max|白色|白色鈦金屬|2|
|iPhone 15 Pro Max|藍|藍色鈦金屬|3|
|iPhone 15 Pro Max|藍鈦|藍色鈦金屬|1|
|iPhone 15 Pro Max|藍鈦色|藍色鈦金屬|1|
|iPhone 15 Pro Max|鈦色|原色鈦金屬|2|
|iPhone 15 Pro Max|銀色|白色鈦金屬|1|
|iPhone 15 Pro Max|黑色|黑色鈦金屬|1|
|iPhone 16|白色|白色|2|
|iPhone 16|粉|粉紅色|1|
|iPhone 16 Plus|白|白色|1|
|iPhone 16 Plus|粉|粉紅色|1|
|iPhone 16 Plus|藍|湛海藍色|1|
|iPhone 16 Pro|原鈦|原色鈦金屬|1|
|iPhone 16 Pro|原鈦色|原色鈦金屬|2|
|iPhone 16 Pro|沙漠色|沙漠色鈦金屬|2|
|iPhone 16 Pro|沙漠金|沙漠色鈦金屬|13|
|iPhone 16 Pro|沙漠鈦|沙漠色鈦金屬|2|
|iPhone 16 Pro|白|白色鈦金屬|4|
|iPhone 16 Pro|白色|白色鈦金屬|5|
|iPhone 16 Pro|金|沙漠色鈦金屬|3|
|iPhone 16 Pro|金色|沙漠色鈦金屬|3|
|iPhone 16 Pro|黑|黑色鈦金屬|2|
|iPhone 16 Pro|黑色|黑色鈦金屬|4|
|iPhone 16 Pro Max|沙漠色|沙漠色鈦金屬|3|
|iPhone 16 Pro Max|沙漠金|沙漠色鈦金屬|4|
|iPhone 16 Pro Max|沙漠鈦|沙漠色鈦金屬|4|
|iPhone 16 Pro Max|白色|白色鈦金屬|6|
|iPhone 16 Pro Max|白色鈦金屬|白色鈦金屬|2|
|iPhone 16 Pro Max|金|沙漠色鈦金屬|1|
|iPhone 16 Pro Max|銀|白色鈦金屬|1|
|iPhone 16 Pro Max|銀色|白色鈦金屬|1|
|iPhone 16 Pro Max|黑|黑色鈦金屬|4|
|iPhone 16 Pro Max|黑色|黑色鈦金屬|4|
|iPhone 16e|白|白色|1|
|iPhone 17|白|白色|5|
|iPhone 17|白色|白色|7|
|iPhone 17|紫|薰衣草紫色|2|
|iPhone 17|紫色|薰衣草紫色|2|
|iPhone 17|綠|鼠尾草綠色|1|
|iPhone 17|綠色|鼠尾草綠色|1|
|iPhone 17|薰衣草|薰衣草紫色|1|
|iPhone 17|藍|霧藍色|1|
|iPhone 17|藍色|霧藍色|2|
|iPhone 17|黑|黑色|1|
|iPhone 17|黑色|黑色|4|
|iPhone 17|鼠尾草綠|鼠尾草綠色|1|
|iPhone 17 Pro|宇宙橙|宇宙橙色|3|
|iPhone 17 Pro|橘|宇宙橙色|9|
|iPhone 17 Pro|橘色|宇宙橙色|7|
|iPhone 17 Pro|橙|宇宙橙色|1|
|iPhone 17 Pro|藍|藏藍色|6|
|iPhone 17 Pro|藍色|藏藍色|1|
|iPhone 17 Pro|藏藍|藏藍色|4|
|iPhone 17 Pro|藏藍色|藏藍色|1|
|iPhone 17 Pro|銀|銀色|9|
|iPhone 17 Pro|銀色|銀色|7|
|iPhone 17 Pro|銀／白|銀色|2|
|iPhone 17 Pro Max|宇宙橘|宇宙橙色|2|
|iPhone 17 Pro Max|橘|宇宙橙色|10|
|iPhone 17 Pro Max|橘色|宇宙橙色|6|
|iPhone 17 Pro Max|橙|宇宙橙色|1|
|iPhone 17 Pro Max|藍|藏藍色|5|
|iPhone 17 Pro Max|藍色|藏藍色|4|
|iPhone 17 Pro Max|藏藍色|藏藍色|4|
|iPhone 17 Pro Max|銀|銀色|9|
|iPhone 17 Pro Max|銀色|銀色|5|
|iPhone 17e|黑|黑色|1|
|iPhone 17e|黑色|黑色|1|
|iPhone 18 Pro|冰川藍|冰川藍色|4|
|iPhone 18 Pro|勃根地紅|勃根地紅色|10|
|iPhone 18 Pro|白|銀色|1|
|iPhone 18 Pro|白色|銀色|1|
|iPhone 18 Pro|紅|勃根地紅色|8|
|iPhone 18 Pro|紅色|勃根地紅色|4|
|iPhone 18 Pro|藍|冰川藍色|1|
|iPhone 18 Pro|藍色|冰川藍色|3|
|iPhone 18 Pro|銀|銀色|5|
|iPhone 18 Pro|銀色|銀色|5|
|iPhone 18 Pro|黑|黑色|4|
|iPhone 18 Pro|黑色|黑色|3|
|iPhone 18 Pro Max|Burgundy|勃根地紅色|1|
|iPhone 18 Pro Max|冰川藍|冰川藍色|21|
|iPhone 18 Pro Max|勃根地紅|勃根地紅色|5|
|iPhone 18 Pro Max|紅|勃根地紅色|12|
|iPhone 18 Pro Max|紅色|勃根地紅色|1|
|iPhone 18 Pro Max|藍|冰川藍色|8|
|iPhone 18 Pro Max|藍色|冰川藍色|2|
|iPhone 18 Pro Max|銀|銀色|5|
|iPhone 18 Pro Max|銀色|銀色|6|
|iPhone 18 Pro Max|黑|黑色|3|
|iPhone 18 Pro Max|黑色|黑色|2|
|iPhone Air|天藍色|天藍色|1|
|iPhone Air|太空黑|太空黑色|1|
|iPhone Air|白|雲白色|1|
|iPhone Air|白色|雲白色|1|
|iPhone Air|雲白色|雲白色|1|
|iPhone Air|黑|太空黑色|2|
|iPhone XS|銀色|銀色|1|

## 前 20 篇解析不到顏色的標題

依既存發文時間新到舊。可能是未標示、不符色盤、多機或歧義；不等於人工確認沒有顏色。

- [販售] 新竹/苗栗iphone 15 pro 256GB
- [販售] 台中 全新iPhone 17 pro max 512G
- [販售] 台中 iPhone 15 pro 256G
- [販售] iphone 17 pro 1tb
- [販售] iphone15pro max 256g
- [販售] 台北 iphone 18 pro max 512g銀/Air 256g
- [販售] 桃園iphone 15 128G 白
- [販售] 台南 Iphone 17 Pm 256G 保內至2027/07
- [販售] iPhone 14 Pro 256g 台中
- [販售] 台北 iPhone 16 Pro Max 256 GB
- [販售] IPhone 12 256G
- [販售] 台北 iPhone 13 Pro+iPad Air 3
- [販售] 二手 iphone11
- [販售] 台北 全新Iphone 17 Pro 256G
- [販售] 板橋 iPhone 17 pro max. 2TB 二手
- [販售] 台南 iPhone 16 Pro 128G 鈦
- [販售] 台中 iPhone 17 pro 256G藍/512G銀
- [販售] 新北 iPhone 16 pro max 256g及airpods pro&airpods pro 2
- [販售] ［販售］雙北 iPhone 16 PLUS 256G
- [販售] 台中 iPhone 14 256G 粉紫

## 機型預覽快照

以下數字均來自排除異常價格後的 data.json。刊登數與可比較樣本數不同：基準組不足 3 篇的文章不算比值。

|容量|顏色|刊登|已售|刊登價中位數|相對值|可比較樣本|
|---|---|---:|---:|---:|---:|---:|
|全部容量|宇宙橙色|19|2|39500|+0%|17|
|全部容量|藏藍色|13|1|35000|+0%|12|
|全部容量|銀色|14|1|36000|+0%|13|
|256GB|宇宙橙色|7|0|39500|+0%|7|
|256GB|藏藍色|9|1|34999|+0%|9|
|256GB|銀色|10|1|35000|+0%|10|
