# 本機日本價格爬蟲（2026-10-30）

`python -m jp.local --data <私人資料庫的 jp 目錄> [--dry-run] [--only pastec,iosys-sell]` 使用家用 IP，來源為 POYU 於 2026-10-30 保存的 HTML。這次僅以離線 fixture 驗收；沒有重新連線或寫入正式資料。安裝與解除排程見 [local/README.md](../local/README.md)。

## 資料與共用邏輯

モバステ買取寫入指定目錄的 `prices.csv`、`latest.csv`、`runs.csv`；イオシス販賣寫入其 `sell/` 子目錄的同名檔案。兩者共用 `jp.buyback` 的 `KEY`、CSV 欄位、時間格式、歷史追加與最新快照更新，販賣價不進買取 CSV。`source_url` 對モバステ是郵送買取規格頁，對イオシス販賣是該組最低價的商品頁；同價時依網址排序選擇，顏色留空。

`buyback.fetch` 新增可選的各站間隔，`validate_rows`、`apply_results` 新增可選的機況清單，原本呼叫的預設值不變。全域請求（含重試）至少相隔 5 秒；pastec.net、iosys.co.jp 各至少 10 秒；駿河屋保留 30 秒設定但沒有啟用抓取；既有 k-tai-iosys.com 仍為 60 秒。每次失敗最多重試一次，全部序列執行。

整個來源的任一頁抓取、解析或分頁失敗，該店整批保留舊價；0 筆、筆數少至少一半、衝突鍵等沿用驗證。其他來源仍可更新，失敗寫私人 `runs.csv`，CLI 回傳非 0。`--dry-run` 同樣驗證既有快照與本次筆數，但不建立資料目錄、CSV 或鎖檔。stdout 只含店家、狀態及筆數。檔案鎖共用於 CLI 與整段本機 Git 同步，固定使用同一份程式庫 checkout。

## モバステ（pastec）買取

從 `https://pastec.net/iphone` 的規格列找郵送買取連結，再讀 `?purchase_type=net` 規格頁；只收既有 `MODELS`、`STORAGES`，17e 不收，不碰 `/api/`。原始目錄含 Duo 與現有目標機型，不靠猜網址增加機型。

範例規格頁 `https://pastec.net/iphone/iphone17pro256gb?purchase_type=net` 的 `.assess__model-card-badges` **明載 SIMフリー**，因此寫入 `carrier=SIMフリー`。若是其他已知電信版本，依明示版本記錄；版本不明或海外版使該店失敗，避免推定為 SIMフリー。列表與規格頁的機型、容量必須一致。

| 頁面機況 | 儲存方式 |
|---|---|
| 新品區的「未開封」 | `未開封` |
| 中古 A／中古 B／中古 C | 取三者最高可收價格，記為 `中古上限` |
| 新品 開封済、ジャンク、不能動作的商品 | 不收 |

主價保留表列價格；範例有橘／藍色減價說明，本版不建立色價列，也不把減價說明算進主價格。未見可靠的價格更新日期時 `shop_updated` 留空，不採頁首新聞日期。裁切規格 fixture 解析為 2 筆。

## イオシス販賣

目錄 `https://iosys.co.jp/items/smartphone/iphone` 的已確認入口如下；Pro 入口同時含 Pro Max，按商品名稱區分。目錄缺少任何既有入口時整店失敗，避免將缺頁當成下架。範例沒有可確認的 Duo 販賣入口，本版未猜測或加入。

| 入口尾段 | 收錄機型 |
|---|---|
| `iphone18_pro` | iPhone 18 Pro／Pro Max |
| `iphone17_pro` | iPhone 17 Pro／Pro Max |
| `iphone_air` | iPhone Air |
| `iphone17?not=pro+17e` | iPhone 17 |

只讀 `#ajax-item-main` 的商品列，不讀推薦商品或其他版面價格。依原 HTML 的 `rel=next` 逐頁收齊，驗證同站、同機型、查詢條件不變與連續頁碼；分頁不完整、循環或超過 100 頁會失敗。完成全部頁面後，每個店家 × 機型 × 容量 × 機況 × 版本取最低刊登價，顏色不分組。

| 頁面機況 | `condition` |
|---|---|
| 未使用品 | `未使用品` |
| 中古Aランク | `中古A` |
| 中古Bランク | `中古B` |
| 中古Cランク | `中古C` |

版本從商品名稱的国内版SIMフリー、docomo／au／SoftBank／Rakuten 版識別；海外版與版本不明的商品不納入。商品名稱的 `ネットワーク利用制限▲` 仍按頁面原有 A／B／C 等級計入；現有欄位沒有獨立保存該限制，最低價可能包含此類商品，查閱時以 `source_url` 的條件為準。若後續要排除或獨立區分，需另定統計規則。

原始 17 Pro 範例首頁有 24 件、共 8 頁；此次裁切保留 7 件（含同規格重複商品、不同容量／機況／版本），聚合為 6 筆。後頁沒有提供真實 HTML，測試中的後頁屬合成變體，未宣稱完成真實全站抓取。

## 駿河屋、Back Market、手機王

駿河屋 `https://www.suruga-ya.jp/kaitori/search_buy?search_word=iPhone` 的 `suruga.html` 有 10 筆書籍／配件結果，唯一明確價格是 iPhone 13 矽膠殼的 1,100 円；其他列是 `kakaku=-1`／メールにてお見積，沒有目標 iPhone 手機報價。因此這份檔案不足以建立手機解析器，也不能據此斷言價格一定由 JavaScript 載入。本版不抓、不寫駿河屋資料。

HTML 未提供可確認的價格 JSON API 網址。後續可先保存精確機型搜尋的 HTML，並檢視檔案引用的 `/drupal/modules/surugaya_buy/assets/js/search_buy_pc.js`、`/drupal/themes/surugaya/js/ansinSearch/kaitori.js`，確認手機商品與價格實際來源；目前未取得這兩個檔案。若之後採集，仍須遵守至少 30 秒同站間隔，不繞過驗證。

Back Market 日本列表 curl 為 403，本版未做。手機王（sogi）條款禁止轉載，因此不抓。網站 `site/` 與 GitHub workflows 均未修改；販賣價的公開呈現及推送後部署留待後續決定。
