# 日本買取頁 HTML fixture

2026-10-07 23:17–23:20 日本時間，以 curl_cffi `impersonate="chrome"`、`Accept-Language: ja-JP,ja;q=0.9` 在 GitHub Actions 依序擷取。イオシス相鄰請求間隔至少 60 秒。原始擷取驗收：https://github.com/iPliny/ptt-iphone-tracker/actions/runs/37635385400

- `mobilemix.html`：https://mobile-mix.jp/?category=7 。保留 18 Pro／Pro Max 六個容量列、緊接的狀態與顏色表單，以及一個非 18 Pro 商品。去除 CSRF、非顏色 input、按鈕、樣式與事件處理器，保留實際商品／價格／色名／減價／不收條件。
- `iosys-pro.html`、`iosys-max.html`：分別擷取 `https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone18-pro/`、`https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone18-pro-max/`；各保留 docomo 與国内版 SIMフリー兩組、四個容量。保留 `.carrer`（原站拼法）、`.name`、`.s-price`、`.a-price`、`.c-price`。
- `amemoba-pro.html`、`amemoba-max.html`：分別擷取 `https://amemoba.com/smartphone/iphone/iphone-18-pro/`、`https://amemoba.com/smartphone/iphone/iphone-18pro-max/`；各保留国内版 SIMフリー與 au 兩組、四個容量，以及原頁 `#h1_date time`。

所有 fixture 的商品與金額皆保留原值；測試的格式變體在測試函式內另行建構。`tests/jp_preview.py` 以這些 fixture 產生**示意歷史**，不代表真實歷史行情，且拒絕寫入專案的 `data/`。
