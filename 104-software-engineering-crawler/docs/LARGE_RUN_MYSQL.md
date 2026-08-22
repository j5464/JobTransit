# 大型爬取、續跑與 MySQL 操作手冊

本手冊對應「Raw 保留歷史，latest JSON 與 MySQL 只保留每職缺最新版本」的設計。請先完成 2 筆 smoke test、30 筆與中型批次，再考慮 10000 筆。目前 77 項離線測試已通過，但尚未執行正式 10000 筆網路爬取，也尚未以使用者的實體 MySQL 密碼寫入資料。

## 1. 儲存邏輯

```text
%LOCALAPPDATA%\job-crawler-104\raw\<run_id>\
├─ search\*.json                 # 淨化後搜尋歷史
├─ detail\*.json                 # 淨化後詳情歷史
├─ manifest.jsonl                # URL、時間、locator、SHA-256
└─ errors.jsonl                  # 如有錯誤才出現

C:\JobData\job-crawler-104\
├─ runs\<run_id>\
│  ├─ jobs_<run_id>.jsonl         # 逐筆 flush，可續跑與重播
│  └─ jobs_<run_id>.csv           # 可選；--no-csv 時沒有
└─ latest\jobs\<ID前兩碼>\
   └─ <job_id>.json                   # 每職缺一檔，只留最新版

MySQL job_crawler_104.jobs             # job_id 主鍵，latest-only
```

Raw 與 run JSONL 是追溯／復原來源；latest JSON 是人工閱讀的目前版；MySQL 是查詢用的目前版。latest JSON 以 job ID 前兩碼分片，避免一個資料夾直接放上萬檔；寫入使用暫存檔與原子 replace，若 replace 失敗，舊 latest 仍然存在。

## 2. 先在 Workbench 確認帳號

Workbench 連線設定目前顯示本機 `localhost:3306` 與使用者 `root`。`root` 是 MySQL 使用者名稱，不是 schema 名稱；程式預設 schema 是 `job_crawler_104`。不要只依 Workbench 連線名稱判斷帳號，請先執行：

```sql
SELECT
    USER() AS connection_identity,
    CURRENT_USER() AS authenticated_account,
    VERSION() AS server_version,
    @@port AS server_port;
```

- `USER()` 是客戶端提供的連線身分。
- `CURRENT_USER()` 是 MySQL 真正用來驗證與授權的帳號；若為 `root@localhost`，`JOB104_MYSQL_USER` 設 `root`。
- 確認 `@@port` 為 `3306`；若不是，後續環境變數使用查詢實值。
- `localhost` 與 Python 預設 `127.0.0.1` 都指向本機，但連線方式由 MySQL 配置決定；若 `127.0.0.1` 失敗，先以 Workbench 實際 host 值設定。

## 3. 由 Workbench 建立 database/table

1. 在 Workbench 開啟本專案的 `sql/001_create_database_and_jobs.sql`。
2. 檢查連線是預期的本機 instance。
3. 執行整份 SQL。
4. 確認最後 `SHOW CREATE TABLE jobs` 成功回傳。

該 SQL 只用 `CREATE ... IF NOT EXISTS`，不包含 `DROP`、`TRUNCATE` 或 `DELETE`。Python 不會自動執行 DDL；同步前只用 `SELECT <預期欄位> FROM jobs LIMIT 0` 檢查 Workbench 建立的表是否符合程式契約。DDL 與 Python 欄位順序也已有離線契約測試。

## 4. PowerShell 連線設定

在 VS Code 專案終端設定：

```powershell
$env:JOB104_MYSQL_HOST = "127.0.0.1"
$env:JOB104_MYSQL_PORT = "3306"
$env:JOB104_MYSQL_DATABASE = "job_crawler_104"
$env:JOB104_MYSQL_USER = "root"
$mysqlPassword = Read-Host "MySQL root password" -AsSecureString
$env:JOB104_MYSQL_PASSWORD = [System.Net.NetworkCredential]::new("", $mysqlPassword).Password
Remove-Variable mysqlPassword
```

只有 `JOB104_MYSQL_PASSWORD` 是必填；其他四項省略時會使用上述預設值。程式直接讀作業系統環境變數，不會自動讀 `.env`；不要把密碼寫入 Python、`pyproject.toml`、`.vscode/launch.json` 或 Git。設在 `$env:` 的值只對當前 PowerShell process 與子 process 有效；關閉終端後需重設。

使用完畢移除密碼：

```powershell
Remove-Item Env:JOB104_MYSQL_PASSWORD
```

## 5. 分階段驗證

先同步環境與執行 77 項離線測試：

```powershell
uv sync
uv run python -m unittest discover -s tests -v
```

然後依序執行：

```powershell
# 2 筆：顯示 Chrome，先驗證線上路徑
uv run python .\run_crawler.py --max-jobs 2 --min-delay 3 --max-delay 4
uv run python .\inspect_results.py

# 檔案確認無誤後，將最新 run 同步到 MySQL
uv run python .\sync_mysql.py
```

在 Workbench 核對：

```sql
USE job_crawler_104;
SELECT COUNT(*) AS latest_job_count FROM jobs;
SELECT job_id, job_title, company_name, quality_status, first_seen_at, last_seen_at
FROM jobs
ORDER BY last_seen_at DESC
LIMIT 20;
```

因為 `jobs.job_id` 是主鍵，同一職缺再次同步只更新 latest。`first_seen_at` 取最早時間，`last_seen_at` 取最新時間；較舊 JSONL 之後重播不會把較新內容覆蓋掉。一批內如有相同 job ID，先去重並留較新 `scraped_at`；每批預設 500 筆一個 transaction，該批任一筆失敗就 rollback。

通過 2 筆後，依序測 30 筆、一個自行選定的中型批次（例如 100 或 500），每階段都檢查 exit code、run summary、JSONL 筆數、latest 檔數、Raw manifest/hash 與 MySQL 筆數。

## 6. 10000 筆命令與預期

建議先寫檔、後同步 MySQL，使網路擷取與資料庫問題可以分開恢復：

```powershell
uv run python .\run_crawler.py `
  --headless `
  --max-jobs 10000 `
  --max-search-pages 1000 `
  --no-csv

uv run python .\inspect_results.py
uv run python .\sync_mysql.py --batch-size 500
```

注意：

- `--max-jobs 10000` 是成功解析目標，不保證 104 當時有 10000 筆符合條件且可成功取得的職缺。搜尋頁耗盡時狀態為 `partial`。
- `--max-search-pages 1000` 是安全上限；若 API 回傳 `lastPage`、空頁或本頁沒有新 ID，會提前停止。
- `--no-csv` 可避免將大量文字又扁平化複製一份；JSONL 仍逐筆 flush，latest JSON 仍每職缺一檔。
- 程式為單線程且每筆至少等 3 秒；10000 × 3 秒已是約 8 小時 20 分的理論最低等待時間，預設 3～6 秒平均僅詳情等待約 12.5 小時，還未計網路、搜尋分頁與失敗略過。
- HTTP 403／429 會立即停止；不要以降低間隔或驗證繞過來「補速度」。
- `data/processed/run_summary_<run_id>.json` 留在專案；大型 JSONL/latest 在 `C:\JobData`；Raw 歷史在 `%LOCALAPPDATA%`。需同時監看這三處剩餘空間。

## 7. 中斷後續跑

從 run summary、`C:\JobData\job-crawler-104\runs` 資料夾或日誌找到 run ID，例如 `20260821T134531+0800`，然後執行：

```powershell
uv run python .\run_crawler.py `
  --headless `
  --max-jobs 10000 `
  --max-search-pages 1000 `
  --no-csv `
  --resume-run 20260821T134531+0800
```

- `--max-jobs` 是這個 run 含舊 JSONL 在內的總目標，不是額外增加數。
- 續跑先串流讀回舊 JSONL，重建已完成 ID 集合與品質統計，也會以通過驗證的 canonical record 重建遺失或損壞的 latest JSON，再 append 新紀錄。
- 原 run 使用 `--no-csv` 時，續跑也必須使用 `--no-csv`。若原 run 有 CSV，續跑不可新增 `--no-csv`；程式會先以 authoritative JSONL 原子重建 CSV，再同時 append 兩者，修復中斷時可能出現的列數差異。JSONL 非空但 CSV 已遺失時會拒絕續跑，避免誤判原 run 的輸出模式。
- 同一 run 再擷取到同名 Raw snapshot 時，會改寫 `_002`、`_003` 新檔，不覆寫舊檔；manifest 因此仍能對應歷史檔案與 hash。
- 續跑完成後，`sync_mysql.py` 讀取整份追加後 JSONL 即可；upsert 可安全重播。
- 長跑時按 `Ctrl+C` 會關閉 HTTP／輸出資源、寫出 `status=interrupted` 摘要，且不會接著啟動 MySQL 同步；使用摘要中的 run ID 續跑即可。

## 8. MySQL 同步選項與復原

獨立同步最近寫入或續跑的 run（依 JSONL 修改時間判定）：

```powershell
uv run python .\sync_mysql.py
```

同步指定 JSONL：

```powershell
uv run python .\sync_mysql.py "C:\JobData\job-crawler-104\runs\<run_id>\jobs_<run_id>.jsonl" --batch-size 500
```

也可讓爬蟲完成後自動同步：

```powershell
uv run python .\run_crawler.py --max-jobs 30 --sync-mysql --mysql-batch-size 500
```

對大型 run，建議使用獨立 `sync_mysql.py`。若 `--sync-mysql` 在爬完後失敗，run summary 會記錄 MySQL 失敗，但已寫入的 Raw、latest 與 JSONL 不會消失；修正連線或 table 後重播 JSONL，不要重爬 104。

常見問題：

- `Access denied`：核對 `CURRENT_USER()`、密碼與 `JOB104_MYSQL_USER`。
- `Can't connect`：確認 MySQL Windows service 正在執行、host 與 port 和 Workbench 一致。
- `Unknown database`：尚未在 Workbench 執行 SQL，或 `JOB104_MYSQL_DATABASE` 不是 `job_crawler_104`。
- `jobs doesn't exist` 或欄位契約錯誤：重新核對 `sql/001_create_database_and_jobs.sql`；程式不會暗中修改 schema。
- 單批失敗：該 transaction 會 rollback；修正問題後重播同一 JSONL。

## 9. 完成準則

每一階段都應同時確認：

1. PowerShell `$LASTEXITCODE` 為 `0`。
2. run summary `status=completed` 且 `record_count/target_count` 達標。
3. `inspect_results.py` 回傳成功，唯一 ID 與必要欄位符合預期。
4. `runs/<run_id>/jobs_<run_id>.jsonl` 可逐列解析；若產生 CSV，其資料列數與 JSONL 一致。
5. latest JSON 每個 job ID 一檔，較舊資料不覆蓋較新資料。
6. Raw manifest 的 locator 對應存在檔案，SHA-256 相符；續跑版本使用 `_002`、`_003` 而非覆寫。
7. Workbench `jobs` 數量是跨 run 之後的「唯一 latest job ID 數」，不一定等於各 run 筆數總和。
8. 報告明確記錄擷取時間、篩選條件、未達標或 blocked/failed 情況，不把網站當次可見資料直接視為市場母體。
