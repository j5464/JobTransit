from __future__ import annotations
from datetime import datetime

from airflow.sdk import dag, task
# 從 tasks 引入剛寫好的建表 Task 邏輯
from tasks.create_silver_tables import create_silver_tables
from tasks.create_gold_tables import create_gold_tables

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
    description="初始化 MySQL Silver & gold 資料表結構",
    schedule=None,  # <--- 設定為 None，表示無定時排程，僅支援手動觸發 (Manual Trigger)
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["init", "mysql", "silver"],
)

@task
def init_silver_tables_dag():
    create_silver_tables()
    create_gold_tables()


init_silver_tables_dag()