from __future__ import annotations

from datetime import datetime, timedelta
import pendulum

from airflow.sdk import dag
from airflow.sdk import task

from tasks.silver_compony import silver_company_mongodb_to_mysql
from tasks.silver_job_language import silver_job_language
from tasks.silver_job_requirement import silver_job_requirement
from tasks.silver_job_specialty import silver_job_specialty
from tasks.silver_job_skill import silver_job_skill
from tasks.silver_job import silver_job_mongodb_to_mysql
from tasks.silver_job_category import silver_category_mongodb_to_mysql


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
    schedule="0 2 * * *",
    start_date=pendulum.datetime(2026, 9, 9, tz="Asia/Taipei"),
    catchup=False,
    tags=["jobtransit", "silver", "etl"],
)
@task
def run_silver_all_etl():
    silver_company_mongodb_to_mysql()
    silver_job_mongodb_to_mysql()
    silver_category_mongodb_to_mysql()
    silver_job_skill()
    silver_job_specialty()
    silver_job_language()
    silver_job_requirement()


run_silver_all_etl()
