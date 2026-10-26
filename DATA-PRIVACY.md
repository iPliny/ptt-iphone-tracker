# 原始資料與公開網站

原始 CSV、抓取紀錄及開發歷史保留於私人儲存庫。正式網站由 Cloudflare Pages 建置，僅發布 `_site/`；不得上傳儲存庫根目錄或 `data/`。

網站不再提供原始 CSV 下載。台灣公開資料沿用既有欄位清單；日本資料僅輸出介面支援的 SIMフリー機型、容量、店家與欄位，抓取狀態只保留頁面需要的時間與狀態，不公開內部錯誤訊息。公開頁面使用的價格、歷史圖表與 JSON 仍可由訪客讀取；這些展示資料不是秘密。

正式網址維持 macshop.crawlsnek.com。GitHub 舊網址由獨立的公開轉址儲存庫接手，該儲存庫不得存放價格原始資料。Cloudflare 預覽網址必須經擁有者登入才能存取。

`.github/workflows/pages.yml` 保留原有排程與 workflow_dispatch 入口，建置並檢查公開產物後，使用 GitHub Actions secret `CLOUDFLARE_PAGES_DEPLOY_HOOK` 觸發 Cloudflare 正式站建置。其他抓取流程仍可呼叫此工作流程。正式分支的 Cloudflare 自動推送部署關閉，以免和部署 Hook 重複；預覽分支保留自動建置。

已公開過的資料無法保證從他人下載、快取或備份中收回。此調整保護後續原始資料存取，不刪除原始檔，也不改寫 Git 歷史。
