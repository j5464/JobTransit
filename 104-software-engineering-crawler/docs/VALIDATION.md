# 驗證紀錄

本文件記錄程式在 2026-08-21 的可重現驗證狀態，並分清楚離線解析測試、線上 smoke test、正式擷取、結果讀回及 Raw 稽核五個層次。最終正式 run 已在 live API 資料路徑的 transport／429、詳情 allow-list、schema `2.0`、transformation `3.0` 與 locator 修改完成後執行；所有線上統計都來自實際輸出，沒有以 fixture、人工補值或臆造資料替代線上職缺。run 後的兩項非輸出路徑修正另由離線測試覆蓋，版本界線在下文說明。

## 驗證範圍與方法

- 固定條件：台灣地區（`area=6001000000`）、軟體／工程類人員（`jobcat=2007001000`）、全職（`ro=1`）。
- 本機環境：Windows、Python 3.13、Google Chrome、Selenium、requests、BeautifulSoup、pandas。
- 數量與節流：已驗證的 live 正式 run 為 30 筆，最短請求間隔 3 秒；CLI 現可設定更大 `--max-jobs`，但尚未實際執行 10000 筆。任何新的大型執行前仍先完成 2 筆 smoke test。
- 工作階段：程式以全新的 Chrome 暫時 profile 開啟固定搜尋頁，動態取得本機 Chrome 版本相符的 User-Agent，再建立獨立 `requests.Session`；headless 模式會正規化 `HeadlessChrome` 執行模式字樣。
- Cookie 界線：不登入 104、不讀取個人 Chrome profile，也不把 Chrome Cookie 搬入 requests；requests 只維持自己在當次工作階段收到的 Cookie。
- 存取界線：未使用第三方 stealth 套件、固定 Chrome 81 UA、CAPTCHA／Cloudflare 破解或登入 Cookie；但 headless 模式會如上所述正規化 UA marker。HTTP 403、429 會立即停止。

線上主流程使用目前觀察到可免登入存取、但沒有官方開發者合約、正式文件或穩定性保證的 `/jobs/search/api/jobs` 與 `/api/jobs/{id}` JSON endpoints。搜尋 endpoint 逐頁提供職缺 ID，詳情 endpoint 提供職缺欄位；保存前會移除 `contact`、`interactionRecord` 及個人化互動狀態，再寫入 Raw JSON snapshot、SHA-256 與 manifest。BeautifulSoup HTML parser 保留給老師教材示範與離線 DOM 回歸，不再承擔目前的線上主流程。

詳情 endpoint 將工作文案提供為純文字，沒有原網頁 DOM 的 `ul/ol/table/dl`；因此 live API 主流程不會宣稱保留不存在的表格或巢狀層級，只保存 API 原生陣列／物件、label/value 與可由明確項目符號辨識的清單。DOM 結構能力只屬於使用 HTML fixture 驗證的 legacy BeautifulSoup parser。

## 離線測試

目前共有 77 項 `unittest` 通過，範圍包括：

- 目前觀察到的搜尋與詳情 JSON endpoints：請求參數、Session、timeout、retry 及錯誤分類。
- API payload 的職缺 ID、全職條件、職缺名稱、公司、地點、薪資、工作內容與條件要求。
- JSON 陣列、`sections[].blocks`、label/value 與工作內容清單抽取。
- 保存 Raw snapshot 前排除聯絡方式與個人化互動狀態，並遮罩明確 Email／手機格式。
- BeautifulSoup 的 `ul/ol`、巢狀清單、`table`、`dl` 離線回歸。
- JSONL、CSV、manifest、穩定 SHA-256、snapshot transformation version、root-relative locator、品質報告、公式注入防護及執行狀態判定。
- 403／429 立即停止、404／410 略過、timeout 與暫時性 5xx retry 設定，以及失敗時關閉 Session。
- 搜尋 endpoint 的傳輸、非法 JSON、root 或 `data` 契約錯誤會讓 run 立即 `failed`；詳情 endpoint 的傳輸或 JSON／root／`data` 契約錯誤連續 3 筆才停止。單一職缺缺必要欄位則記錄後略過。
- API 與 HTML parser 的 `job.description.items` 共用 item schema 契約。
- API 與 HTML parser 都要求 job ID、職稱、公司與 narrative description；HTML 工作 metadata 不會被誤當成 description。Canonical schema `2.0` 在兩個 parser 間共用完整 `source` 鍵集合，舊 run 的 `1.0` 可明確區分。
- `C:\JobData\job-crawler-104` 預設 data root、run JSONL/CSV 串流 flush、`--no-csv`、上萬筆參數、續跑跳過已完成 ID 與 latest 修復。
- latest JSON 依 job ID 前兩碼分片、較舊時間不覆蓋較新版，原子 replace 失敗時仍保留舊檔。
- 續跑如遇到同名 Raw snapshot，使用 `_002`、`_003` 新檔，不覆寫舊 snapshot 或破壞舊 manifest/hash 對應。
- MySQL 環境變數、canonical-to-column 投影、內容 hash、批次去重、latest-only 時間守門、commit/rollback、JSONL 串流重播與 schema 預檢；測試使用 fake connection，不會寫入使用者 MySQL。
- Workbench DDL 與 Python `MYSQL_COLUMNS` 欄位契約，以及 SQL 不含 `DROP`、`TRUNCATE` 或 `DELETE`。

重跑命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

若交付前再增加測試，最終文件應以最後一次命令輸出更新；77 是本紀錄撰寫時的已通過數量。

## 大型儲存與 MySQL 驗證邊界

新增功能將可覆寫的大型資料根目錄改為 `C:\JobData\job-crawler-104`，每個 run 逐筆寫入 `runs/<run_id>/jobs_<run_id>.jsonl`，另以 `latest/jobs/<ID前兩碼>/<job_id>.json` 保留每職缺最新 canonical 版本。Raw 仍在 `%LOCALAPPDATA%\job-crawler-104\raw\<run_id>` 依 run 保留歷史；續跑遇到同名檔時增加 `_002`、`_003`，不覆寫既有檔案。

MySQL 部分只管理一張 latest-only `job_crawler_104.jobs` 表，`job_id` 為主鍵，常用 scalar 欄位單獨建欄，陣列與完整 canonical record 使用 JSON 欄位。較舊 `last_seen_at` 不覆蓋較新內容，`first_seen_at` 保留最早值。Python 只連線 Workbench 已建好的 schema/table，不執行 DDL；建表由使用者在 Workbench 手動執行 `sql/001_create_database_and_jobs.sql`。Workbench 連線設定已顯示 `root` 與本機 `localhost:3306`，但仍要用 `SELECT USER(), CURRENT_USER(), VERSION(), @@port` 核對實際驗證帳號與 port。

下列事項目前只有離線驗證，不得宣稱已完成 live 大型驗證：

- 尚未執行正式 10000 筆網路爬取。
- 尚未使用使用者的 MySQL 密碼對實體 `jobs` 表寫入。
- 尚未用實際大型產出量測量磁碟使用量、續跑時間、MySQL 同步耗時或網站當時可見職缺上限。

因此下一階段必須依 `docs/LARGE_RUN_MYSQL.md` 用 2 筆、30 筆、中型批次和最後 10000 筆逐階驗證，每階段都檢查 exit code、run summary、JSONL/latest/Raw 一致性與 MySQL 查詢結果。

## 技術演進背景

最初以 Selenium 直接解析渲染後 HTML 時，一般互動瀏覽器看得到職缺，但自動化工作階段的廣泛搜尋顯示「共 0 筆」；這被正確記為軟性拒絕，不是「市場職缺為 0」。接著依早期文章測試舊 `/jobs/search/list`，匿名透明請求得到 HTTP 403，顯示舊端點／舊範例已不適合目前頁面。

後續檢視目前網站的資料流程，主程式改用目前觀察到可免登入存取的 `/jobs/search/api/jobs` 與 `/api/jobs/{id}`，並由本機 Chrome 動態取得版本相符的 User-Agent。這保留 requests Session 的教學邏輯，同時避免硬編文章中的 Chrome 81 字串；它不搬用個人登入 Cookie，也不破解 CAPTCHA。這些 endpoints 沒有官方開發者合約或相容性保證，舊 HTML 與舊 list endpoint 的失敗紀錄因此保留作為技術演進及錯誤判讀案例。

較早的正式 API run `20260821T015236+0800` 雖成功取得 30 筆，但發生在最終遞迴 sanitizer、搜尋 allow-list、schema `2.0` 與 root-relative locator 完成前；它只保留為技術演進與舊 Raw 風險案例，不作為最終版本的驗證結果。

## 線上執行結果

| 用途 | run ID | 狀態 | 目標 | 成功 | 結果 |
|---|---|---:|---:|---:|---|
| 最終 API 正式執行 | `20260821T022416+0800` | `completed` | 30 | 30 | live API 資料路徑核心修改與 429 修正均已完成 |
| 最終 live API smoke test | `20260821T023212+0800` | `completed` | 2 | 2 | 2 unique、全職、全部 `ok`、六欄 0 缺失 |

正式 run 使用 canonical schema `2.0` 與 snapshot transformation `3.0`，並在 429 明確不經 urllib3 `Retry-After` 自動重試的修正後執行，因此驗證了 live API 主流程的固定台灣／職類／全職篩選、列表 ID、詳情請求、淨化、schema、locator 與當時輸出。`20260821T023212+0800` 又以更新後的 live API 主流程成功驗證 2 筆。這些 live runs 早於新增的大型 data root、latest 分片、續跑與 MySQL 功能；新功能目前由 77 項離線測試覆蓋，不將既有 30/30 說成已驗證完整新工作樹或 10000 筆流程。

最終正式 run 的讀回檢查結果：

- 實際 30 筆，唯一職缺 ID 30 個，重複 0 筆。
- `quality.status` 全部為 `ok`（30 筆），沒有 `partial` 或解析警告。
- 職缺名稱、公司名稱、工作地點、薪資待遇、工作內容、條件要求六個主要欄位的缺失數皆為 0。
- 工作性質全部為全職（30 筆）。
- 輸出的 job ID 與搜尋第 1 頁前 30 個通過 URL／ID 與全職條件檢核的有效 ID 完全相同，沒有以其他樣本替換。
- 地區分布：台北市 14、桃園市 8、台中市 4、新北市 2、高雄市 1、新竹市 1。
- 薪資原始值中，「待遇面議」19 筆；其餘 11 筆為明確月薪區間、下限或固定月薪。

這 30 筆只代表 `20260821T022416+0800` 當次固定條件下成功可見的公開職缺，不是 104 全部軟體工程市場的母體，也不能拿地區或薪資次數直接推論整體比例。

## Raw 與隱私驗證

目前 Raw 來源是 JSON，而不是 Selenium `page_source`：

歷史 run `20260821T015236+0800` 完成後的審查發現，當時版本雖已排除 API 的 `contact` 物件，但 4 份本機詳情 snapshot 的工作文字仍含格式類似 Email／手機的來源內容。這批舊 Raw 因 manifest 與 SHA-256 稽核需求沒有事後改寫，只能留在本機、不可散布；它只作為 sanitizer 演進案例。最終正式 run `20260821T022416+0800` 是另外建立的新 artifacts，已套用遞迴聯絡資訊遮罩、搜尋 metadata allow-list、解析／全職驗證後才保存詳情，以及 transformation `3.0`。

```text
%LOCALAPPDATA%\job-crawler-104\raw\<run_id>\
├─ search\page_001.json
├─ detail\<job_id>.json
└─ manifest.jsonl
```

- 詳情 payload 在寫檔前先排除 `contact`、`interactionRecord` 與 header 內的儲存、追蹤、應徵狀態；文字遞迴遮罩明確 Email、台灣手機與市話。
- 最終正式 run 的 Raw 稽核計數為：`forbidden_key_matches=0`、`unredacted_email_matches=0`、`mobile_matches=0`、`landline_matches=0`。
- manifest 有 31 筆 entries，磁碟上也有 31 份對應 snapshots（1 份搜尋＋30 份詳情）；`hash_mismatch=0`。每筆 manifest 都記錄 `capture_method=requests.Session.get`、`media_type=application/json`、來源 URL、時間、locator 與 SHA-256。
- canonical record 以 `source.raw_sha256` 連回對應的淨化後 snapshot。`raw_sha256` 用來驗證同一 transformation version 下 snapshot 位元組是否相同；跨 run 判斷職缺 canonical 內容是否變更，應使用排除 run 時間／Raw 路徑的 `content_sha256` 或比對明確 canonical 欄位。
- canonical JSONL／CSV、manifest 與 run summary 使用 `raw-root://<run_id>/...` 形式的 root-relative locator；實際讀檔時去掉 scheme，再以當次設定的 Raw root 解譯。正式 artifacts 的 `absolute_c_users_path_matches=0`，避免洩漏 Windows 帳號名稱，也讓資料可搬到其他電腦。
- manifest 分別標記搜尋 allow-list 與詳情欄位 allow-list／遞迴遮罩，並保存 transformation version；目前規則版本為 `3.0`。`raw_sha256` 主要用於同一 transformation 規則下的位元組完整性核對。
- 最終正式 CSV 具有 UTF-8 BOM，含 1 列 header 與 30 列職缺資料；讀回列數與 JSONL 的 30 筆一致。
- Raw JSON 位於 `%LOCALAPPDATA%`，沒有提交 Git；即使已淨化，仍不可公開散布完整職缺原文。

## Smoke test 通過標準

未來重新執行時仍應先跑：

```powershell
uv run python .\run_crawler.py --max-jobs 2 --min-delay 3 --max-delay 4
```

只有以下條件全部成立，才可執行 30 筆：

- PowerShell 的 `$LASTEXITCODE` 為 `0`。
- `data\processed\run_summary_<run_id>.json` 的 `status` 為 `completed`。
- 目標與成功筆數為 `2/2`。
- 兩筆都能回讀 JSONL；必要欄位 `job_id`、`title`、`company`、`description` 不為空，`employment_type_raw` 明確等於「全職」，且品質報告沒有無法解釋的 API schema 警告。

只要狀態為 `blocked`／`failed`、成功數小於 2、HTTP 403／429，或 API 回傳與一般頁面矛盾的 0 筆，就立即停止。不要因終端機印出「摘要」字樣而視為完成，也不要改用個人登入 Cookie 或驗證繞過程式。

## 技術參考的採用界線

- [alex6226/104_job_analyze](https://github.com/alex6226/104_job_analyze)：用來比較搜尋列表、職缺 ID、逐筆詳情與輸出流程。其程式碼針對舊頁面，且目前參考頁沒有提供足以讓本專案直接複製整合的明確授權依據；因此沒有逐字複製。
- [JiaTool：104 人力銀行職缺爬蟲](https://blog.jiatool.com/posts/job104_spider/)：用來理解早期 JSON list/detail 與 requests Session 設計。目前實作延續「列表 ID → 詳情」概念，但改用目前觀察到可免登入、且沒有官方合約的 endpoints；User-Agent 由本機 Chrome 動態取得，沒有硬編 Chrome 81。

本專案保留的可重現設計是：小批量、明確篩選、動態 Chrome UA、獨立 requests Session、列表取得 ID、詳情允許清單、保存前淨化、Raw 來源雜湊、品質檢查與遇阻停止。

## 結論

- 離線解析、串流輸出、latest/續跑與 MySQL 儲存契約共有 77 項測試通過。
- live API data path 的正式 run `20260821T022416+0800` 已完成 30/30；更新後 live API smoke run `20260821T023212+0800` 已完成 2/2。新增的大型儲存／MySQL 功能在這些 live runs 之後才加入，尚未執行 10000 筆網路驗證或實體 MySQL 寫入。
- 最終正式結果為 30 個唯一職缺、30 筆全職、30 筆全部 `ok`、0 重複，六個主要欄位缺失皆為 0；輸出等於搜尋第 1 頁前 30 個有效 ID。
- 31 筆 manifest entries 與 31 份 snapshots 一一對應，`hash_mismatch=0`；Raw forbidden keys、Email、手機、市話及正式輸出的 `C:\Users` 絕對路徑比對數皆為 0。CSV 有 BOM 與 30 筆資料。
- API endpoint 沒有 DOM 結構，因此上述成功不代表取得了原網頁的 `ul/ol/table/dl`；live pipeline 沒有捏造這些結構。
- 沒有偽造資料、沒有把 fixture 當成真實職缺，也沒有提交 Raw JSON。
