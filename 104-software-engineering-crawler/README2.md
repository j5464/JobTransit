步驟 1：開啟終端機 (Terminal / PowerShell / Git Bash)
請打開你電腦上的終端機（例如 VS Code 的 Terminal、PowerShell 或 Git Bash）。

步驟 2：執行 Docker 指令建立並啟動 MySQL 容器
在終端機中，一次複製並執行以下這整行指令：

docker run -d \
  --name mysql-container \
  -p 3307:3306 \
  -e MYSQL_ROOT_PASSWORD=password \
  -e MYSQL_DATABASE=TESTDB \
  mysql:latest

指令說明：
-docker run：建立並啟動一個新的 Docker 容器。

-d：讓容器在背景執行（Background Mode），不會佔用終端機畫面。

--name mysql-container：將這個容器命名為 mysql-container（方便之後識別與管理）。

-p 3307:3306：將本機電腦的 3307 Port 映射到容器內部的 3306 MySQL Port。(設定為 3307 是為了避免跟電腦地端原本已安裝的 MySQL 衝突)

-e MYSQL_ROOT_PASSWORD=password：設定 MySQL 的管理員 (root) 密碼為 password。

-e MYSQL_DATABASE=TESTDB：資料庫一啟動時，自動建立一個名為 TESTDB 的預設資料庫。

-mysql:latest：自動從 Docker Hub 下載最新的 MySQL 官方映像檔（Image）來執行。

步驟 3：確認容器是否成功啟動
執行以下指令，檢查容器的運行狀態：

docker ps

如果看到列表中出現 mysql-container，且 STATUS 顯示為 Up，PORTS 顯示 0.0.0.0:3307->3306/tcp，就代表 MySQL 容器已經在你的 Docker 上完全建立成功並正常運行中！