# 顏色解析與比較預覽

查證日期：2026-10-07。正式名稱以 [Apple 台灣辨識 iPhone 機型](https://support.apple.com/zh-tw/108044) 為準，涵蓋目前 listings.csv 的有效型號；不存在的 `iPhone X Pro` 不建立色盤。

特別核對：[iPhone 17 Pro 台灣新聞稿](https://www.apple.com/tw/newsroom/2025/09/apple-unveils-iphone-17-pro-and-iphone-17-pro-max-the-most-powerful-and-advanced-pro-models-ever/) 正式名稱為「宇宙橙色／藏藍色」，而非需求範例的「宇宙橘色／深藍色」；後兩者仍接受為別名。[iPhone 18 Pro 台灣規格](https://www.apple.com/tw/iphone-18-pro/specs/) 已核實「黑色／銀色／冰川藍色／勃根地紅色」，無須使用未核實名稱。紅色系列保存為 `(PRODUCT)RED`（統一括號字形）。

`tracker.py:COLOR_TABLE` 是模組層級對照表，Pro Max、Plus、mini 共用對應系列色盤。中文色名的完整名稱、去掉尾端「色」及表內別名都接受；英文不分大小寫。別名是文章用語的人工對照，不代表 Apple 自稱使用這些別名。

解析來源依序為 [顏色]、[規格]、[容量]、[型號] 第一個非空行、去掉 [販售] 的標題；第一個含顏色的來源若衝突或不符該型號色盤就留空，不向下猜測。不掃全文；先排除配件顏色與現金、銀行等非色彩用詞。多機或多容量標題保守留空。單一來源的白／銀若對應同一標準色則不算衝突。

舊 CSV 缺 color 仍能讀取；補值只用標題、不抓文章、不寫事件。新本文解析不到時保留舊色。多品項檔案及週報不改。

網站先執行既有異常價格排除，再以單支文章計算顏色統計。每篇除以同型號、同容量、同為全新或二手的刊登價中位數；基準組至少 3 篇（含未標色的有效價格），某顏色至少 3 篇能算比值才公開價格與相對值。相對值取比值中位數減 1，再四捨五入至整數百分比。全部容量原始刊登價中位數仍受容量與新舊組成影響，排序與上方摘要用校正後相對值；四捨五入後相同則明示並列。已售數是文章狀態，不是真實成交價。

## 正式顏色與別名

|系列（Max／Plus／mini 同色盤）|標準名稱|額外別名|
|---|---|---|
|iPhone 8|銀色|銀、白、白色、Silver、White|
|iPhone 8|金色|金、Gold|
|iPhone 8|太空灰色|灰、灰色、黑、黑色、太空灰、Space Gray、Space Grey、Black|
|iPhone 8|(PRODUCT)RED|紅、紅色、Red、PRODUCT RED、（PRODUCT）RED|
|iPhone XS|銀色|銀、白、白色、Silver、White|
|iPhone XS|金色|金、Gold|
|iPhone XS|太空灰色|灰、灰色、黑、黑色、太空灰、Space Gray、Space Grey、Black|
|iPhone 11|黑色|黑、Black|
|iPhone 11|白色|白、White|
|iPhone 11|綠色|綠、Green|
|iPhone 11|紫色|紫、Purple|
|iPhone 11|黃色|黃、Yellow|
|iPhone 11|(PRODUCT)RED|紅、紅色、Red、PRODUCT RED、（PRODUCT）RED|
|iPhone 11 Pro|銀色|銀、白、白色、Silver、White|
|iPhone 11 Pro|金色|金、Gold|
|iPhone 11 Pro|太空灰色|灰、灰色、黑、黑色、太空灰、Space Gray、Space Grey、Black|
|iPhone 11 Pro|夜幕綠色|綠、綠色、夜幕綠、Midnight Green、Green|
|iPhone 12|黑色|黑、Black|
|iPhone 12|白色|白、White|
|iPhone 12|藍色|藍、Blue|
|iPhone 12|綠色|綠、Green|
|iPhone 12|紫色|紫、Purple|
|iPhone 12|(PRODUCT)RED|紅、紅色、Red、PRODUCT RED、（PRODUCT）RED|
|iPhone 12 Pro|銀色|銀、白、白色、Silver、White|
|iPhone 12 Pro|金色|金、Gold|
|iPhone 12 Pro|石墨色|石墨、灰、灰色、黑、黑色、Graphite、Black|
|iPhone 12 Pro|太平洋藍色|藍、藍色、太平洋藍、Pacific Blue、Blue|
|iPhone 13|藍色|藍、Blue|
|iPhone 13|綠色|綠、Green|
|iPhone 13|粉紅色|粉、粉色、粉紅、Pink|
|iPhone 13|(PRODUCT)RED|紅、紅色、Red、PRODUCT RED、（PRODUCT）RED|
|iPhone 13|星光色|星光、白、白色、Starlight、White|
|iPhone 13|午夜色|午夜、黑、黑色、Midnight、Black|
|iPhone 13 Pro|銀色|銀、白、白色、Silver、White|
|iPhone 13 Pro|金色|金、Gold|
|iPhone 13 Pro|石墨色|石墨、灰、灰色、黑、黑色、Graphite、Black|
|iPhone 13 Pro|天峰藍色|藍、藍色、天峰藍、Sierra Blue、Blue|
|iPhone 13 Pro|松嶺青色|綠、綠色、松嶺青、松嶺綠、Alpine Green、Green|
|iPhone 14|藍色|藍、Blue|
|iPhone 14|紫色|紫、Purple|
|iPhone 14|黃色|黃、Yellow|
|iPhone 14|(PRODUCT)RED|紅、紅色、Red、PRODUCT RED、（PRODUCT）RED|
|iPhone 14|星光色|星光、白、白色、Starlight、White|
|iPhone 14|午夜色|午夜、黑、黑色、Midnight、Black|
|iPhone 14 Pro|銀色|銀、白、白色、Silver、White|
|iPhone 14 Pro|金色|金、Gold|
|iPhone 14 Pro|太空黑色|黑、黑色、太空黑、Space Black、Black|
|iPhone 14 Pro|深紫色|紫、紫色、深紫、Deep Purple、Purple|
|iPhone 15|黑色|黑、Black|
|iPhone 15|藍色|藍、Blue|
|iPhone 15|綠色|綠、Green|
|iPhone 15|黃色|黃、Yellow|
|iPhone 15|粉紅色|粉、粉色、粉紅、Pink|
|iPhone 15 Pro|黑色鈦金屬|黑、黑色、黑鈦、黑鈦色、黑色鈦、Black、Black Titanium|
|iPhone 15 Pro|白色鈦金屬|白、白色、白鈦、白鈦色、白色鈦、銀、銀色、White、White Titanium、Silver|
|iPhone 15 Pro|原色鈦金屬|原鈦、原鈦色、原色鈦、原色鈦金、原鈦金、鈦色、自然鈦、原色、Natural、Natural Titanium|
|iPhone 15 Pro|藍色鈦金屬|藍、藍色、藍鈦、藍鈦色、藍色鈦、Blue、Blue Titanium|
|iPhone 16|黑色|黑、Black|
|iPhone 16|白色|白、White|
|iPhone 16|粉紅色|粉、粉色、粉紅、Pink|
|iPhone 16|湖水綠色|綠、綠色、湖水綠、Teal、Green|
|iPhone 16|湛海藍色|藍、藍色、湛海藍、Ultramarine、Blue|
|iPhone 16 Pro|黑色鈦金屬|黑、黑色、黑鈦、黑鈦色、黑色鈦、Black、Black Titanium|
|iPhone 16 Pro|白色鈦金屬|白、白色、白鈦、白鈦色、白色鈦、銀、銀色、White、White Titanium、Silver|
|iPhone 16 Pro|原色鈦金屬|原鈦、原鈦色、原色鈦、原色鈦金、原鈦金、鈦色、自然鈦、原色、Natural、Natural Titanium|
|iPhone 16 Pro|沙漠色鈦金屬|沙漠金、沙漠鈦、沙漠鈦色、沙漠色、沙漠、金、金色、Desert、Desert Titanium、Gold|
|iPhone 16e|黑色|黑、Black|
|iPhone 16e|白色|白、White|
|iPhone 17|黑色|黑、Black|
|iPhone 17|白色|白、White|
|iPhone 17|霧藍色|霧藍、藍、藍色、Mist Blue、Blue|
|iPhone 17|鼠尾草綠色|鼠尾草綠、綠、綠色、Sage、Green|
|iPhone 17|薰衣草紫色|薰衣草、薰衣草紫、紫、紫色、Lavender、Purple|
|iPhone 17 Pro|銀色|銀、白、白色、Silver、White|
|iPhone 17 Pro|宇宙橙色|宇宙橙、宇宙橘色、宇宙橘、橙、橙色、橘、橘色、Cosmic Orange、Orange|
|iPhone 17 Pro|藏藍色|藏藍、深藍色、深藍、藍、藍色、Deep Blue、Blue|
|iPhone Air|太空黑色|太空黑、黑、黑色、Space Black、Black|
|iPhone Air|雲白色|雲白、白、白色、Cloud White、White|
|iPhone Air|天藍色|天藍、藍、藍色、Sky Blue、Blue|
|iPhone Air|淺金色|淺金、金、金色、Light Gold、Gold|
|iPhone 17e|黑色|黑、Black|
|iPhone 17e|白色|白、White|
|iPhone 17e|嫩粉色|嫩粉、粉、粉色、粉紅、粉紅色、Soft Pink、Pink|
|iPhone 18 Pro|黑色|黑、Black|
|iPhone 18 Pro|銀色|銀、白、白色、Silver、White|
|iPhone 18 Pro|冰川藍色|冰川藍、藍、藍色、Glacier Blue、Blue|
|iPhone 18 Pro|勃根地紅色|勃根地紅、紅、紅色、Burgundy、Burgundy Red、Red|
