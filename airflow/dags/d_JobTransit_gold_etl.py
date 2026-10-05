from __future__ import annotations

from datetime import datetime, timedelta
import pendulum

from airflow.sdk import dag

from tasks.gold_page1 import run_pipeline_page1
from tasks.gold_page2 import run_pipeline_page2
from tasks.gold_page4 import run_pipeline_page4
from tasks.gold_page3 import run_pipeline_page3


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="d_JobTransit_silver_etl",
    default_args=default_args,
    description="清洗 MongoDB job_details 並寫入 MySQL Silver 表",
    schedule=None,  # <--- 設定為 None，表示無定時排程，僅支援手動觸發 (Manual Trigger)
    start_date=pendulum.datetime(2026, 9, 9, tz="Asia/Taipei"),
    catchup=False,
    tags=["jobtransit", "silver", "etl"],
)

def run_silver_all_etl():
    t1 = run_pipeline_page1()
    t2 = run_pipeline_page2()
    t3 = run_pipeline_page4()
    t4 = run_pipeline_page3()

    t1 >> t2 >> t3 >> t4


run_silver_all_etl()
