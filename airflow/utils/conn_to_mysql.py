from __future__ import annotations

import os

from dotenv import load_dotenv
from pymysql import connect

# 載入 .env 檔案中的環境變數，讓資料庫設定可被外部配置
load_dotenv()


# 建立與 MySQL 的連線，並回傳連線物件
# 若有參數傳入，會覆蓋環境變數；否則會使用預設值
# 例如：MYSQL_DB、MYSQL_USER、MYSQL_PASSWORD、MYSQL_HOST、MYSQL_PORT

def conn_to_mysql(
    # db_name: str | None = None,
    # user: str | None = None,
    # password: str | None = None,
    # conn_ip: str | None = None,
    # port: int | None = None,
):
    #載入.env 到環境變數
    load_dotenv()
    # 若參數未傳入，則從環境變數取得；若環境變數未設定，再使用預設值
    db_name = os.getenv("MYSQL_DATABASE")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_ROOT_PASSWORD")
    conn_ip = os.getenv("MYSQL_HOST")
    # port 轉整數防呆
    raw_port = os.getenv("MYSQL_PORT")
    port = int(raw_port) if raw_port else 3307

    print(f"Connecting to: host={conn_ip}, port={port}, user={user}, db={db_name}")
    try:
        # 建立 MySQL 連線
        return connect(
            host=conn_ip,
            port=port,
            user=user,
            password=password,
            database=db_name,
            connect_timeout=10,  # 10秒連不上自動拋出例外
            read_timeout=30,     # 讀寫超過30秒自動中斷，避免無效卡死
            autocommit=False
        )
    except Exception as exc:
        print(f"連線失敗，請確認 MySQL 伺服器是否有啟動。錯誤訊息: {exc}")
        return None
