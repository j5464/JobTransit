# 104 軟體／工程類人員職缺爬蟲

這是一個可直接用 VS Code 開啟的獨立 Python 專案。搜尋範圍已固定為：

- 網站：104 人力銀行公開職缺頁
- 地區：台灣地區（`area=6001000000`）
- 職類：軟體／工程類人員（`jobcat=2007001000`）
- 工作性質：全職（`ro=1`）
- 預設目標：成功解析 30 筆職缺

程式架構沿用黃彬華老師教材的主要邏輯：

`建立 client → 逐頁 fetch → 逐筆 parse → 每筆立即寫入 Raw/latest/run spool → 選擇性批次同步 MySQL`

目前線上主流程會先由本機 Chrome 動態取得版本相符的 User-Agent，再以獨立的 `requests.Session` 讀取目前觀察到可免登入存取、但沒有官方開發者合約或穩定性保證的 `/jobs/search/api/jobs` 與 `/api/jobs/{id}` JSON endpoints；另外加入職缺 ID 去重、Raw JSON 歷史 snapshot、巢狀結構保存、每職缺一個 latest JSON、上萬筆也不需整批放入記憶體的串流 JSONL，以及可選的 MySQL latest-only upsert。老師教材風格的 BeautifulSoup HTML 解析器仍保留，供離線教材示範與 DOM 回歸測試使用。

### 與既有規劃對齊

- 搜尋不加關鍵字，保留 `jobcat=2007001000`「軟體／工程類人員」底下目前可見的全部子職務，並固定台灣地區與全職。
- 去重主鍵使用職缺 URL 中的 104 job ID，不以可能重複或變動的公司名稱＋職稱代替。
- 這次 30 筆是用來驗證擷取技術、資料字典與清洗流程的樣本，不是市場母體；不能直接拿它估計台灣軟體職缺總量或比例。

## 1. 使用界線

本程式只讀取不需登入即可看到的公開職缺資料，不載入個人 Cookie、不登入帳號、不投遞履歷，也不使用 `curl-cffi` 或 CAPTCHA 破解。Chrome 只用全新的暫時 profile 取得本機版本相符的 User-Agent；`--headless` 模式會把同版本 UA 的 `HeadlessChrome` 執行模式字樣正規化為 `Chrome`。Chrome Cookie 不會搬入 `requests.Session`，HTTP Session 只維持自己在當次執行收到的 Cookie。HTTP 403／429 會立即停止；搜尋 endpoint 若發生傳輸、非法 JSON、根節點或 `data` 契約錯誤，整個 run 立即標為 `failed`。詳情 endpoint 的傳輸或 JSON／root／`data` 契約錯誤則按候選累計，連續 3 筆才停止；404／410 與單一職缺缺必要欄位只記錄並略過，繼續尋找後續有效職缺。

網站條款與 API 結構可能改變。每次執行前，應重新確認 [104 會員規約](https://accounts.104.com.tw/terms)、[104 求職規約](https://www.104.com.tw/info/terms)與 [robots.txt](https://www.104.com.tw/robots.txt)；若相關路徑被列為 `Disallow` 就不要執行。目前未取得 104 對自動擷取的明確授權，本範例使用單執行緒及 3～6 秒隨機間隔，只能視為保守的本地課堂研究設計。不得公開轉售或重新發布完整職缺文案、Raw JSON 或整批資料。

詳情 API 的 `contact`、`interactionRecord` 及 header 內個人化互動狀態會在保存前排除；允許保存的文字中，格式明確的 Email、台灣手機與市話也會遮罩。Raw JSON 仍包含職缺頁原文，因此預設存到不在專案內的 `%LOCALAPPDATA%\job-crawler-104\raw`，並依 `run_id` 保留歷史；它只能留在本機研究環境，不應上傳 Git、雲端分享或公開散布。可覆寫的 latest JSON 與 MySQL `jobs` 表只保留每個 `job_id` 最新版本，不會取代 Raw 歷史。

## 2. 專案結構

```text
104-software-engineering-crawler/
├─ .python-version                 # 與老師教材相同概念：標示 Python 3.13
├─ pyproject.toml                  # 專案資訊與最小相依套件
├─ .venv/                          # 初始化後產生，不提交 Git
├─ .vscode/                        # VS Code interpreter、測試及執行設定
├─ run_crawler.py                  # 爬蟲入口
├─ inspect_results.py              # 讀回結果與品質檢查入口
├─ sync_mysql.py                  # 將既有 run JSONL 重播至 MySQL，不重爬
├─ sql/
│  └─ 001_create_database_and_jobs.sql # 由 Workbench 手動建立 schema/table
├─ src/job_crawler_104/
│  ├─ crawler.py                   # Chrome 啟動、API 分頁、節流與主流程
│  ├─ api_client.py                # requests Session、timeout、retry、HTTP 錯誤
│  ├─ api_parser.py                # 目前觀察到的 JSON payload → canonical schema
│  ├─ parser.py                    # BeautifulSoup HTML 教材／離線回歸解析器
│  ├─ config.py                    # 固定搜尋條件與目前觀察到的 endpoint URL
│  ├─ paths.py                     # 專案、Raw 與大型 data root 路徑
│  ├─ storage.py                   # Raw JSON、串流 JSONL/CSV、manifest
│  ├─ persistence.py               # 分片 latest JSON 與 MySQL latest-only upsert
│  ├─ mysql_cli.py                  # MySQL 重播命令
│  ├─ quality.py                   # 缺失率、重複值與分布統計
│  ├─ inspection.py                # 結果讀回命令
│  ├─ cli.py                       # PowerShell/VS Code 參數入口
│  └─ errors.py                    # 明確錯誤類型
├─ tests/                          # 不連網的解析器與輸出測試
└─ data/
   └─ processed/                   # 品質報告與執行摘要（小型專案記錄）

C:/JobData/job-crawler-104/             # 預設大型 data root，不放 OneDrive
├─ runs/<run_id>/
│  ├─ jobs_<run_id>.jsonl      # 逐筆 flush 的完整本次 run
│  └─ jobs_<run_id>.csv        # 預設有；--no-csv 時不產生
└─ latest/jobs/<ID前兩碼>/
   └─ <job_id>.json                # 每職缺一檔，只保留最新版

%LOCALAPPDATA%/job-crawler-104/raw/
└─ <run_id>/                       # 依 run 保留 search/detail Raw 歷史、錯誤與 manifest
```

將 Raw JSON 和大型輸出分別放在專案外，是為了降低專案位於 OneDrive 等同步資料夾時意外上傳原始資料、並避免上萬個小檔反覆同步。請仍自行確認作業系統或備份軟體沒有同步 `%LOCALAPPDATA%` 與 `C:\JobData`。

## 3. 需要安裝什麼

電腦端先準備：

1. Python 3.13（64 位元）。
2. Google Chrome 最新穩定版。
3. VS Code，以及 Microsoft 的 Python、Pylance 擴充套件。

PowerShell 不屬於爬蟲套件；Windows 通常已內建。這裡只是把它當成 VS Code 的命令列，用來建立 `.venv`、安裝 Python 套件與執行程式，不需要另外「安裝 PowerShell」。

`pyproject.toml` 只安裝本案真正需要的套件：

- `selenium`：啟動全新 Chrome 工作階段，取得目前安裝版本相符的 User-Agent。
- `requests`：共用 HTTP Session 取得目前觀察到的搜尋與詳情 JSON，並提供 timeout、retry 與狀態碼檢查。
- `urllib3`：提供 `requests` adapter 的暫時性 5xx retry 規則；因程式直接 import，故明確列為直接依賴。
- `beautifulsoup4`：保留老師教材的 CSS selector HTML 解析，以及 `ul/ol`、`table`、`dt/dd` 離線回歸測試。
- `pandas`：後續讀取、清理與分析輸出；爬取階段的 CSV 由 Python 標準庫串流寫入。
- `pymysql[rsa]`：在 Workbench 先建好資料庫後，將 run JSONL 分批 upsert 至 MySQL；程式本身不執行 DDL。

沒有照搬老師整份課程環境中的 Kaggle、MongoDB、繪圖、財經等無關套件。Selenium 4 已包含 Selenium Manager，因此本案不重複安裝 `webdriver-manager`；第一次執行時它可能需要連網取得與 Chrome 相容的 driver。

## 4. 全新專案初始化（PowerShell）

先用 VS Code 開啟整個專案資料夾，而不是只開單一 `.py`：

```powershell
Set-Location "C:\Projects\104-software-engineering-crawler"
code .
```

`C:\Projects\104-software-engineering-crawler` 只是可攜式範例；請替換成你實際建立或複製專案的位置。若能選擇，建議不要把含有研究資料的專案放在 OneDrive、Dropbox 等自動同步資料夾。

確認 Python 版本並建立隔離環境：

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
```

上述命令刻意直接呼叫 `.venv` 裡的 Python，因此不必修改 PowerShell 的 Execution Policy，也不必先執行 `Activate.ps1`。`-e .` 表示以 editable mode 安裝目前專案；修改 `src/` 後不需反覆重裝。

如果電腦已安裝老師可能使用的 `uv`，也可以在專案根目錄改用：

```powershell
uv sync
```

兩種方法擇一即可，不要同時建立兩套環境。接著在 VS Code 按 `Ctrl+Shift+P`，執行 `Python: Select Interpreter`，選擇：

```text
<專案資料夾>\.venv\Scripts\python.exe
```

`.vscode/settings.json` 已預設指向這個位置。

## 5. 先執行解析器測試

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

這就是「解析器測試」：它不連 104，而是把固定 JSON fixture 丟進 `parse_job_detail_api()`，並把固定 HTML fixture 丟進 `parse_search_page()`、`parse_job_detail()`。測試會確認職稱、公司、薪資、地點、工作內容、條件、API 陣列，以及 `ul/ol`、`table`、`dl` 都會轉成預期結構。同一套離線測試也覆蓋串流輸出、latest JSON 分片，以及以 fake connection 驗證的 MySQL 批次 upsert/rollback，不會更動你的 MySQL。如此可區分「網路／瀏覽器／資料庫連線問題」與「解析或儲存邏輯問題」。2026-08-21 目前版本共有 77 項離線測試通過；交付前若增加測試，應以最後一次命令輸出為準。

## 6. 執行爬蟲

第一次建議先做 2 筆 smoke test。預設會短暫顯示全新的 Chrome 視窗，用來開啟固定搜尋頁並讀取 `navigator.userAgent`；後續職缺資料由 `requests.Session` 取得：

```powershell
uv run python .\run_crawler.py --max-jobs 2 --min-delay 3 --max-delay 4
```

命令結束後先檢查 `$LASTEXITCODE`，再開啟專案內的 `data\processed\run_summary_<run_id>.json`。只有同時符合以下三項，才執行預設 30 筆：

1. `$LASTEXITCODE` 為 `0`。
2. 摘要的 `status` 為 `completed`。
3. 摘要顯示目標 2 筆且成功 2 筆（`2/2`）。

若 `status` 是 `blocked` 或 `failed`，或成功數未達 2，應立即停止並閱讀摘要、日誌與 Raw 診斷檔；終端機出現「完成摘要」這個標題本身不代表爬取成功。

確認 smoke test 完整成功後，才執行預設 30 筆：

```powershell
uv run python .\run_crawler.py
```

日後確認環境穩定，才選擇讓 Chrome 的啟動階段使用背景模式：

```powershell
uv run python .\run_crawler.py --headless
```

也可直接在 VS Code 的「執行與偵錯」選擇 smoke、30 筆、10000 筆、續跑、檢查與 MySQL 同步設定。常用參數：

```text
--max-jobs 30             成功解析的總目標筆數；至少 1，大型測試可設 10000
--max-search-pages 1000   搜尋結果最多翻頁數；仍會在 API lastPage/無新 ID 時提前停
--min-delay 3             每次請求間最短等待秒數，不接受低於 3 秒
--max-delay 6             最長等待秒數
--timeout 25              Chrome 首頁載入與 readyState 顯式等待秒數
--headless                不顯示 Chrome 視窗
--data-root <路徑>     latest 與 run exports；預設 C:\JobData\job-crawler-104
--raw-root <路徑>      Raw 歷史根目錄；預設 %LOCALAPPDATA%\job-crawler-104\raw
--no-csv                 只串流寫 JSONL，不產生重複資料的 CSV
--resume-run <run_id>    續跑既有 run，讀回 JSONL 並跳過已完成 job_id
--sync-mysql             爬完後將本次 JSONL 批次 upsert 到既有 jobs 表
--mysql-batch-size 500   MySQL 每個 transaction 的筆數
```

`--max-jobs` 已無 30 筆上限，但「10000」是目標而非網站一定有足夠可用職缺的保證。搜尋頁用完時 run 會是 `partial`。本版本已有 77 項離線測試，但尚未進行正式 10000 筆網路執行；請先依 [`docs/LARGE_RUN_MYSQL.md`](docs/LARGE_RUN_MYSQL.md) 從 2、30、中型批次逐階驗證，再開始 10000 筆。

大型執行建議不同時產生 CSV，並先完成檔案爬取再獨立同步 MySQL：

```powershell
uv run python .\run_crawler.py --headless --max-jobs 10000 --max-search-pages 1000 --no-csv
uv run python .\sync_mysql.py
```

若中途停止，以同一個 run ID 續跑；`--max-jobs 10000` 表示含既有資料在內的總目標，不是再加 10000 筆。原 run 使用 `--no-csv` 時，續跑也必須保留該參數；原 run 已有 CSV 時則不可在續跑新增 `--no-csv`，避免 JSONL／CSV 筆數分岔：

```powershell
uv run python .\run_crawler.py --headless --max-jobs 10000 --max-search-pages 1000 --no-csv --resume-run <run_id>
```

## 7. 程式流程與欄位對應

1. `build_search_url()` 固定組出可供人工核對的台灣地區、軟體／工程類人員、全職搜尋網址。
2. `bootstrap_api_session()` 建立全新的 Chrome 暫時 profile，開啟固定搜尋頁並以 JavaScript 取得本機版本相符的 User-Agent；不讀個人 profile，也不搬運 Chrome Cookie。headless 模式只正規化執行模式字樣，不硬編版本號。
3. `create_api_session()` 把動態取得的 User-Agent 放進獨立 `requests.Session`。Session 自行維持該次 HTTP 工作階段的 Cookie；HTTP 500～504 有有限次 retry，每次 retry 也至少等待 3 秒並加 0～3 秒 jitter，403／429 則立即停止。
4. `fetch_search_page()` 逐頁讀取目前觀察到的 `/jobs/search/api/jobs`，固定帶入 `area`、`jobcat`、`ro=1`；`iter_api_candidates()` 以 104 職缺 ID 去重並再次檢查全職代碼，直到成功筆數達標或搜尋頁耗盡。
5. `fetch_job_detail()` 逐筆讀取目前觀察到的 `/api/jobs/{id}`；每次請求間維持 3～6 秒隨機間隔。兩個 endpoints 當下可免登入讀取，但沒有官方開發者合約或相容性保證。
6. `_sanitized_detail()` 在保存前移除 `contact`、`interactionRecord` 及 `isSaved`、`isFollowed`、`isApplied` 等個人化互動狀態。
7. 搜尋 snapshot 取得後即淨化保存；詳情則先完成必要欄位與全職檢核，再保存淨化後 JSON，避免留下沒有 manifest 的孤立檔。每份檔案都計算 SHA-256；manifest 記錄實際 JSON endpoint URL、時間、路徑、雜湊、`application/json` 媒體類型，以及 snapshot transformation version。
8. `parse_job_detail_api()` 只投影允許清單中的欄位：職缺名稱、公司、地點、薪資、工作內容，以及經歷、學歷、科系、語文、工具、技能與其他條件。
9. API 中的陣列會保留為 JSON list，主要區段另存 `sections[].blocks` 與 `key_value.items`；工作內容中的項目符號／編號行也會抽成分析用清單。
10. `parser.py` 的 BeautifulSoup HTML 解析流程不參與目前線上擷取，但仍可用 fixture 驗證 `ul/ol`、巢狀清單、`table`、`dl` 與 DOM 改版情境。

重要限制：目前詳情 JSON endpoint 把工作文案提供為純文字，因此線上 API 主流程無法取回原網頁 DOM 的 `ul/ol/table/dl`，也不會憑空猜測表格或巢狀層級。它會保留 API 原生陣列／物件、label/value，以及從純文字明確項目符號抽出的清單。只有未來能合法取得實際詳情 HTML 並交給 `parser.py` 時，才可保留 DOM 的有序清單、巢狀清單、表格與定義清單結構。
11. 每筆通過必要欄位與全職檢查後，依序寫入 Raw snapshot、`C:\JobData\job-crawler-104\latest\jobs\<ID前兩碼>\<job_id>.json` 與本次 run JSONL。latest 用暫存檔加原子取代，且較舊的 `scraped_at` 不會覆蓋較新版本。
12. run JSONL 每筆立即 flush，不把上萬筆全部放入記憶體；CSV 也可串流寫入，或用 `--no-csv` 略過。`--resume-run` 會讀回原 JSONL、先重建遺失／損壞的 latest JSON，並以 JSONL 原子重建既有 CSV，再跳過已完成 ID 並繼續 append；同一 run 再取得的 Raw snapshot 改用 `_002`、`_003` 新檔名，不覆寫舊 snapshot 或使舊 manifest/hash 失效。長跑時按 `Ctrl+C` 會產生 `interrupted` 摘要並略過後續 MySQL 同步，保留 run ID 供續跑。
13. 爬取完成後才建立品質報告與 run summary；`status=completed` 且成功筆數達標才回傳 exit code 0。若指定 `--sync-mysql`，再將本次 JSONL 以預設 500 筆一 transaction 的方式 latest-only upsert。

API 與 HTML 兩個 parser 都把 `job_id`、職缺名稱 `title`、公司 `company`、工作內容 `description` 視為必要欄位；任一缺少時不輸出空白假資料。線上主流程另要求 `employment_type_raw` 必須明確等於「全職」，否則略過該筆。薪資、地點、條件要求等選填欄位缺少時則保留該筆、填入 `null`，並將 `quality.status` 標為 `partial`。HTML parser 的工作內容只取 narrative blocks，不會把工作待遇、地點等 metadata 拼成假的 description。

## 8. 輸出格式

`C:\JobData\job-crawler-104\runs\<run_id>\jobs_<run_id>.jsonl` 是 canonical schema 的最完整本次 run 輸出；「完整」是相對於扁平化 CSV 而言，不代表它對來源 API 無損。API parser 只投影允許欄位，且會正規化／遮罩文字；需要追溯未投影欄位時，應使用經淨化的 Raw JSON snapshot。JSONL 每一列是一個 JSON object，canonical schema 內的巢狀 list/dict 會保持原生結構，繁體中文不會轉成 `\uXXXX`；每筆 flush，中途停止時已完成資料仍在。

目前 canonical `schema_version` 為 `2.0`：`job.description.items` 在 API 與 HTML parser 都固定使用 `{text, children}` item 物件，`source` 同時保留 JSON／HTML 兩組 provenance 欄名，不適用者填 `null`。舊 run 的 `1.0` 不應與 `2.0` 直接合併，應先做明確 migration。

`C:\JobData\job-crawler-104\latest\jobs\<ID前兩碼>\<job_id>.json` 是人工閱讀與單筆處理用的最新 canonical 版本。用 job ID 而非職缺名稱當檔名，可避免重複名稱、Windows 非法字元與職名變更；以前兩碼分片，可避免單一資料夾直接擺放上萬檔。寫入使用暫存檔及原子 replace；replace 失敗時舊 latest 仍保留，不會先刪掉舊檔。

`C:\JobData\job-crawler-104\runs\<run_id>\jobs_<run_id>.csv` 是預設產生的分析方便版本。常用欄位是一職缺一列；`tools_json`、`skills_json`、`sections_json` 等仍是合法 JSON 字串，可用 `json.loads()` 還原。CSV 採 UTF-8-SIG，並針對 `= + - @` 開頭的文字做 Excel 公式注入防護；JSONL 保留的是 sanitizer 與 parser 處理後的 canonical 值，不是未修改的 API 來源字串。大型 run 建議用 `--no-csv`，以避免同一批文字同時保存 JSONL 與 CSV。

`%LOCALAPPDATA%\job-crawler-104\raw\<run_id>\search\page_001.json` 與 `detail\<job_id>.json` 是 requests 取得並在保存前淨化的 JSON snapshot。相同 run 續跑時如遇到同名 snapshot，會新增 `page_001_002.json`、`page_001_003.json` 等版本，不覆寫舊檔。相同 run 下的 `manifest.jsonl` 記錄每份資料的請求 URL、擷取時間、root-relative locator、媒體類型、SHA-256 與 transformation version；若使用 `--raw-root`，則以指定目錄取代預設位置。canonical JSONL／CSV 只保存像 `raw-root://<run_id>/detail/<job_id>.json` 這類相對於 Raw root 的 locator，不寫入展開後的 `%LOCALAPPDATA%` 絕對路徑，因此不會把 Windows 帳號名稱帶進分析輸出。讀取 snapshot 時，去掉 `raw-root://` 後，以當次 `--raw-root`（或預設 Raw root）解析 locator。這些 snapshot 已排除聯絡與互動狀態，但仍可能含完整職缺原文，不能提交 Git。

MySQL `job_crawler_104.jobs` 是可查詢的 latest-only 投影：`job_id` 為主鍵，相同 ID 只更新較新 `last_seen_at` 的內容，`first_seen_at` 保留最早時間。常用欄位單獨建欄，陣列使用 MySQL JSON，完整 canonical record 保存在 `canonical_json`。MySQL 不保留每次歷史；歷史來源仍以 Raw/run artifacts 追溯。

## 9. 讀回結果

```powershell
uv run python .\inspect_results.py
```

程式會自動從 `C:\JobData\job-crawler-104\runs` 讀取最新 JSONL（也可在命令列明示指定檔案），檢查：

- 實際筆數與該 run summary 中 `target_count` 的差距。
- 職缺 ID 唯一數與重複數。
- 職稱、公司、地點、薪資、工作內容、條件要求的缺失率。
- `ok/partial` 解析狀態與警告。
- 縣市、工作性質與薪資原始字串分布。

完整結果另存到專案內的 `data/processed/inspection_jobs_<run_id>.json`。

## 10. MySQL latest-only 設定

你的 MySQL Workbench 連線設定已顯示本機 `localhost:3306` 與使用者 `root`，但 `root` 是使用者名稱，不是資料庫名稱。執行 SQL 前仍應在 Workbench 用以下唯讀查詢確認實際驗證帳號和 port：

```sql
SELECT USER(), CURRENT_USER(), VERSION(), @@port;
```

若 `CURRENT_USER()` 回傳例如 `root@localhost`，Python 端的 `JOB104_MYSQL_USER` 使用 `root`。請在 Workbench 手動開啟並執行 [`sql/001_create_database_and_jobs.sql`](sql/001_create_database_and_jobs.sql)；Python 只會驗證欄位契約與 upsert，不會自動建庫、建表、DROP 或清除既有資料。

PowerShell 環境變數皆只需對當前終端有效：

```powershell
$env:JOB104_MYSQL_HOST = "127.0.0.1"
$env:JOB104_MYSQL_PORT = "3306"
$env:JOB104_MYSQL_DATABASE = "job_crawler_104"
$env:JOB104_MYSQL_USER = "root"
$mysqlPassword = Read-Host "MySQL root password" -AsSecureString
$env:JOB104_MYSQL_PASSWORD = [System.Net.NetworkCredential]::new("", $mysqlPassword).Password
Remove-Variable mysqlPassword
```

建議先爬完、檢查 JSONL，再重播至 MySQL：

```powershell
uv run python .\sync_mysql.py
```

`sync_mysql.py` 省略路徑時會選 `C:\JobData\job-crawler-104\runs` 中最後修改（包括最近續跑）的 JSONL；也可將特定 `jobs_*.jsonl` 當第一個參數。它不會重新連線 104。同一份 JSONL 可重複同步，因為 `job_id` 主鍵與時間守門使操作具有冪等性。同步後可在 Workbench 查詢：

```sql
USE job_crawler_104;
SELECT COUNT(*) AS latest_job_count FROM jobs;
SELECT job_id, job_title, company_name, last_seen_at
FROM jobs
ORDER BY last_seen_at DESC
LIMIT 20;
```

完成後可用 `Remove-Item Env:JOB104_MYSQL_PASSWORD` 從當前 PowerShell 終端移除密碼。完整 Workbench、續跑、大型執行與故障復原步驟請見 [`docs/LARGE_RUN_MYSQL.md`](docs/LARGE_RUN_MYSQL.md)。

## 11. 後續資料清洗建議

清洗應建立新的 processed 資料，不覆寫 Raw JSON、JSONL 或 `*_raw` 欄位。

1. 先依 `source_job_id` 去除同一次執行的重複；跨日期資料不要直接刪除，因同一職缺可能更新內容，可用 `raw_sha256` 判斷淨化後來源 JSON 是否變更。
2. 薪資先分類為月薪、年薪、時薪、論件、待遇面議，再解析上下限。`待遇面議（經常性薪資達 4 萬元或以上）` 只表示揭露門檻，不等同精確月薪 40,000。
3. 地點可從 `location_raw` 抽出縣市、行政區與其餘地址；多地點、遠端、海外支援或「或」分隔內容需另設旗標，不能只用固定字數切割。
4. `experience_raw`、`education_raw` 保留原文，再新增標準化欄位；「不拘」與缺失值不是同一件事。
5. `tools_json`、`skills_json` 先 `json.loads()`，再做同義詞映射，例如 `ReactJS → React`、`Github → GitHub`；不要用簡單字串 contains 把 `Java` 誤配到 `JavaScript`。
6. 工作內容與其他條件可先正規化空白、項目符號與換行；中文斷詞、技能抽取放在 processed 階段，並保留原文供追溯。
7. 缺失 scalar 使用 `null/None`，確定存在但沒有項目的 collection 使用 `[]`，不要把缺失轉成字面字串 `"None"` 或 `"nan"`。
8. 若資料來自 HTML parser，`sections[].blocks` 的 `list`、`table`、`definition_list` 應依 `type` 分流後再展開；保留清單的有序／無序屬性、巢狀層級、表格欄名與原列序。API 主流程只有 `paragraph`／`key_value` 與明確項目符號投影時，不要誤標成 DOM 表格或巢狀清單。
9. 展開一對多欄位時另建長表，例如 `job_skills`、`job_tools`、`job_section_items`，並保留 `source_job_id`、區段名稱、清單層級與項目順序，避免寬表因多值欄位重複職缺列。
10. 每個衍生欄位都要記錄轉換規則與版本；對薪資、技能或地點抽取做抽樣人工覆核，並將無法確定的值標為待確認，而非強制猜測。
11. 報表中要註明擷取日期、固定篩選條件、執行狀態與「只代表該次可見公開職缺」，避免把 30 筆樣本推論成整體母體。若執行狀態不是 `completed`，不能把 0 筆或殘缺結果解讀成市場沒有職缺。
12. 正式專題的跨日資料應採 snapshot 模型：每次擷取保留 `snapshot_at`，另依 job ID 維護 `first_seen`、`last_seen`，並以標準化內容計算 `content_hash`；`content_hash` 用於判斷分析欄位是否改變，`raw_sha256` 主要驗證當次淨化後 Raw JSON 的位元組完整性。只有 transformation version 相同時才可比較 Raw hash，兩者用途不要混用。
13. Raw 詳情 API 已保留 `industry`、`employees`、`salaryMin`、`salaryMax`、`salaryType`、`remoteWork` 等來源欄位，可在後續 Silver 層投影成產業、公司規模、薪資上下限／型態與遠端旗標。建立欄位前先用多筆 snapshot 核對代碼與單位，保留來源值及轉換版本，不要僅憑欄名猜測。

## 12. 常見問題

- `NoSuchDriverException`：確認 Chrome 已安裝且可正常開啟；保持網路連線，讓 Selenium Manager 取得相容 driver。
- 搜尋／詳情 API 回傳 403 或 429：程式會標成 `blocked` 並立即停止。稍後降低頻率再試，不要加入 CAPTCHA 繞過、stealth 或個人登入 Cookie。
- 搜尋 API 發生傳輸錯誤、回應不是合法 JSON、root 非物件或缺少 `data` 清單：run 立即 `failed`。詳情 API 的傳輸或 JSON／root／`data` 契約錯誤連續 3 筆才停止；404／410 或單筆缺必要職缺欄位會記錄後略過。各情況都應先查看 run summary、`errors.jsonl` 與 manifest，再更新 fixture 和測試，不要直接把錯誤欄位填空。
- Chrome 搜尋頁顯示「共 0 筆」，但一般瀏覽器有職缺：這是早期 HTML/Selenium 路線遇到的軟性拒絕；目前主流程已改讀當下觀察到可免登入存取、但沒有官方合約的 JSON endpoints。若搜尋 endpoint 本身也回 0 筆，仍視為可能的工作階段異常並停止，不把它解讀成市場沒有職缺。
- User-Agent 每次由本機 Chrome 動態取得版本；headless 模式只正規化 `HeadlessChrome` 字樣，不需手工硬編 Chrome 81 或其他版本。程式也不複製個人 Chrome Cookie；若 Chrome 版本更新，只需保持 Chrome 與 Selenium driver 相容。
- PowerShell 不允許 `Activate.ps1`：不需調整系統政策，照本說明直接使用 `.\.venv\Scripts\python.exe`。
- VS Code 顯示找不到套件：重新選擇 `.venv\Scripts\python.exe`，再執行 `python -m pip install -e .`。
- `Access denied for user`：先用 Workbench 的 `CURRENT_USER()` 核對帳號，確認當前 PowerShell 已設 `JOB104_MYSQL_PASSWORD`；密碼不要寫進 `launch.json`、Python 或 Git。
- `Unknown database` 或 `Table 'job_crawler_104.jobs' doesn't exist`：Python 不會自動建表，請先在 Workbench 執行 `sql/001_create_database_and_jobs.sql`。
- MySQL 同步失敗：爬取的 Raw、latest 與 run JSONL 已先寫入；修正連線後執行 `uv run python .\sync_mysql.py <JSONL路徑>` 即可重播，不用重爬。

## 13. 技術參考與驗證狀態

本專案比較過使用者提供的 [alex6226/104_job_analyze](https://github.com/alex6226/104_job_analyze) 與 [JiaTool：104 人力銀行職缺爬蟲](https://blog.jiatool.com/posts/job104_spider/)。兩者有助於理解「搜尋列表取得職缺 ID，再逐筆解析詳情」以及共用 requests Session 的流程，但其中是較早期的 `/jobs/search/list`、頁面 selector 與固定 Chrome 81 User-Agent。現在的實作採用目前觀察到可免登入存取、但沒有官方合約的 `/jobs/search/api/jobs`、`/api/jobs/{id}`，並由本機 Chrome 動態取得版本相符的 User-Agent，沒有硬編舊版本，也沒有搬入個人登入 Cookie。GitHub 參考頁目前未提供足以讓本專案直接複製整合的明確授權依據，因此本專案沒有逐字搬用其程式碼，而是自行實作並用 fixture 回歸測試。

2026-08-21 目前共有 77 項離線測試通過。正式 run `20260821T022416+0800` 已包含 API transport／429、詳情 allow-list、schema `2.0`、transformation `3.0` 與 locator 等 live API 資料路徑核心修改，結果為 `completed`、30/30；後續 live API smoke run `20260821T023212+0800` 為 `completed`、2/2、2 個唯一 ID、全部 `ok`／全職，六個主要欄位缺失皆為 0。新增的 `C:\JobData` 路徑、latest 原子分片、串流輸出、續跑 Raw 不覆寫、Workbench DDL/Python 欄位契約、MySQL 批次 upsert/rollback 皆已由離線測試覆蓋；正式 10000 筆網路執行與實體 MySQL 資料寫入尚未執行，不將離線成功說成線上大量驗證完成。

正式稽核確認：30 個唯一 job ID、30 筆全職、30 筆全部 `ok`、六個主要欄位缺失皆為 0；輸出 ID 與搜尋第 1 頁前 30 個有效 ID 完全相同。Raw manifest 共 31 筆（1 份搜尋＋30 份詳情），所有 SHA-256 都與 snapshot 相符；Raw 中聯絡鍵、未遮罩 Email、手機與市話計數皆為 0。CSV 有 UTF-8 BOM 與 30 筆資料列，canonical／manifest／summary locator 沒有 `C:\Users` 絕對路徑。API 純文字無法還原 DOM 結構的限制仍然存在。完整稽核與舊版技術演進請見 [`docs/VALIDATION.md`](docs/VALIDATION.md)。
