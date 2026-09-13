from __future__ import annotations
from datetime import datetime

from airflow.sdk import dag, task
# 從 tasks 引入剛寫好的建表 Task 邏輯
from tasks.create_silver_tables import _load_conn_to_mysql, create_silver_tables

default_args = {
    "owner": "airflow",
    "retries": 1,
}

# -----------------------------------------------------------------------------
# 這一段是 DAG (負責排程、執行條件與呼叫 Task)
# -----------------------------------------------------------------------------
@dag(
    dag_id="d_init_silver_tables",
    default_args=default_args,
    description="初始化 MySQL Silver 層 7 張資料表結構",
    schedule="@once",  # 開機/載入時自動執行一次
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["init", "mysql", "silver"],
)
def init_silver_tables_dag():

    @task
    def run_create_tables():
        # 呼叫 tasks/ 裡面的邏輯
        conn_to_mysql = _load_conn_to_mysql()
        engine = conn_to_mysql(db_name="TESTDB")
        create_silver_tables(engine)
        print("Silver tables created successfully!")

    # 執行 Task
    run_create_tables()

init_silver_tables_dag()