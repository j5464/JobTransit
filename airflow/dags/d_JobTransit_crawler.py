from datetime import datetime, timedelta

import pandas as pd
from airflow.sdk import dag
from tasks.airflow_job_id import get_job_id
from tasks.job_detail import each_job_web
from tasks.export_to_json import save_jobs_to_json


# Default arguments for the DAG
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email": ["zsxc13579@gmail.com"],
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

@dag(
    dag_id="d_JobTransit_crawler",
    default_args=default_args,
    description="An example DAG with Python operators",
    schedule="* 10 10 * *",
    start_date=datetime(2026, 9, 1),
    catchup=False,
    tags=["example", "decorator"]  # Optional: Add tags for better filtering in the UI
)
def JobTransit_crawler():
    get_job_id()
    each_job_web()

# 主執行
JobTransit_crawler()
