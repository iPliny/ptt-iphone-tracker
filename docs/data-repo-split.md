# 程式與私人資料拆分交接

本 PR 僅準備程式，尚未生效。main 的 data/ 完整保留，不改寫歷史、不更改可見性。先完成設定和分支驗收，再交 Claude 覆核；不能先合併再補 secrets。

## 私人資料庫與權限（停止點一，POYU 確認）

1. 建立私人 `iPliny/ptt-iphone-data`，main 根目錄直接保存原 `data/` 的全部內容（包括 jp/、column/、blog/、weekly/，不再多包 data/）。保留一份本機備份，核對檔案清單與雜湊；不要只搬 CSV。
2. 產生 fine-grained token，只選資料庫，Contents: Read and write、Metadata: Read，存入程式庫 secret `DATA_REPO_TOKEN`，設定到期提醒。不要在對話貼 token。
3. Cloudflare token 限指定帳戶的 Cloudflare Pages: Edit，存為 `CLOUDFLARE_API_TOKEN`；帳戶 ID 存為 `CLOUDFLARE_ACCOUNT_ID`。
4. 保留既有 Pages 專案、網域及預覽 Access。Git 專案可在關閉所有自動分支建置後用 Wrangler 直接上傳，無須重建成另一個專案。正式與預覽自動建置皆須關閉；舊 Hook 在驗收通過、切換完成後才移除，避免中途停更。

## 分支驗收（設定後才執行）

本 PR 保留所有正式寫入／部署 job 的 main 限制。不得直接 dispatch 本分支後把 skipped 當成功，也不得直接取消限制寫正式資料。

下一階段在受信任驗收分支增加臨時 workflow：私人資料使用獨立測試分支，track 縮短掃描範圍；jp 依現有規則先 dry-run，再以獨立測試流程驗證資料庫提交；Pages 以非 main 名稱部署，確認預覽 Access 保護。不得啟動正式部署、不提交或輸出原始資料到程式庫。驗收後移除臨時 workflow 與資料測試分支。驗證輸出只放 PR 描述。

確認 checkout → 抓取／寫入 → push/rebase（保留三次重試）→ 公開產物建置 → Cloudflare 上傳均成功。log 只含公開文章資訊與統計；原始 CSV 路徑仍為 404。

## 正式切換（停止點二，等 Claude 覆核）

- 先停用並等待既有資料寫入 workflows 全部結束，避免複製後又有新資料寫回程式庫；記錄原本啟用狀態，切換後恢復。
- 從凍結的最新 main 再同步一次完整 data/ 至私人資料庫，核對雜湊。不要用準備階段的舊快照覆蓋新資料。
- Claude 覆核通過才合併；依核准步驟另做移除程式庫已追蹤 data/ 的 commit，不改寫歷史。此 PR 不包含資料刪除。
- 停用 Cloudflare 正式及預覽 Git 自動建置，避免空資料建置覆蓋網站。驗證直接上傳後停止舊 Hook，恢復抓取、週報、部署與 watchdog。
- 手動執行一次並觀察第一輪排程：新 commit 只出現在私人資料庫；程式庫沒有 data/ 追蹤檔；網站資料正常，CSV 404。

## 改公開（停止點三，POYU 再確認）

只有 POYU 確認後才改程式庫公開。先檢查 main 追蹤檔、所有其他分支／PR 與 Actions log/artifact，確認截止點之後的新資料未留在任何將公開的 ref 或輸出。`.gitignore` 不會移除已追蹤檔或 Git 歷史。

**截止點必須明確記錄到 commit／時間。**「過去公開過的不收回」不等於私人期間新增資料也可公開；若私人期間有新資料 commit，先列出時間與範圍交 POYU 確認，再決定可見性，不擅自改寫歷史。

## 日誌與測試

- 日本 dry-run 原本會印出所有解析列，正式執行也印出含 error 的 runs 列；改為只印 shop/status/rows，原始 CSV 寫入邏輯不變。
- tracker 的既有 log 主要為公開文章網址、事件與統計；不新增原始資料輸出。健康 summary 仍只含統計及固定警訊。
- CI sparse checkout 排除 data/，不帶資料 token。原本依賴真實資料的兩個測試改用既有合成 fixture；原始資料輸出防護測試保留。

參考：https://developers.cloudflare.com/pages/configuration/git-integration/
