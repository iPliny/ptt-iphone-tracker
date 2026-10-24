# 日本買取頁 HTML fixture

2026-10-07 23:17–23:20 日本時間，以 curl_cffi `impersonate="chrome"`、`Accept-Language: ja-JP,ja;q=0.9` 在 GitHub Actions 依序擷取。イオシス相鄰請求間隔至少 60 秒。原始擷取驗收：https://github.com/iPliny/ptt-iphone-tracker/actions/runs/37635385400

- `mobilemix.html`：https://mobile-mix.jp/?category=7 。保留 18 Pro／Pro Max 六個容量列、緊接的狀態與顏色表單，以及一個非 18 Pro 商品。去除 CSRF、非顏色 input、按鈕、樣式與事件處理器，保留實際商品／價格／色名／減價／不收條件。
- `iosys-pro.html`、`iosys-max.html`：分別擷取 `https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone18-pro/`、`https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone18-pro-max/`；各保留 docomo 與国内版 SIMフリー兩組、四個容量。保留 `.carrer`（原站拼法）、`.name`、`.s-price`、`.a-price`、`.c-price`。
- `amemoba-pro.html`、`amemoba-max.html`：分別擷取 `https://amemoba.com/smartphone/iphone/iphone-18-pro/`、`https://amemoba.com/smartphone/iphone/iphone-18pro-max/`；各保留国内版 SIMフリー與 au 兩組、四個容量，以及原頁 `#h1_date time`。

所有 fixture 的商品與金額皆保留原值；測試的格式變體在測試函式內另行建構。`tests/jp_preview.py` 以這些 fixture 產生**示意歷史**，不代表真實歷史行情，且拒絕寫入專案的 `data/`。

## 2026-10-24 Duo 真實頁面

由本機既有 `jp.buyback.fetch` 依序取得（遵守節流），未遇封鎖，未使用代理。

- mobile-mix：https://mobile-mix.jp/?category=7
- イオシス：https://k-tai-iosys.com/pricelist/smartphone/iphone/iphone-duo/
- アメモバ：https://amemoba.com/smartphone/iphone/iphone-duo/ （從 iPhone 列表確認入口）

- `mobilemix-duo.html`：原始 HTML SHA-256 `b4b7aa91d84159c78c898953b2caa2ed61d76f1a159154714c0f9d24860aadb9`；保留全部 Duo 商品列、價格與 mobile-mix 色價控制項，移除連結與非解析欄位。
- `iosys-duo.html`：原始 HTML SHA-256 `88ff5a847539bfe9f4e61780123718ee9640ff5ea6609a0a0facc5ba54755820`；保留全部 Duo 商品列、價格與 mobile-mix 色價控制項，移除連結與非解析欄位。
- `amemoba-duo.html`：原始 HTML SHA-256 `1e5b07292481dbb829980f630764a565a8e04b4600ec1c8592d5f349e8979f0d`；保留全部 Duo 商品列、價格與 mobile-mix 色價控制項，移除連結與非解析欄位。

海外版排除／混入別機型的測試變體由上述片段明確替換產生，不當作真實店家報價。
