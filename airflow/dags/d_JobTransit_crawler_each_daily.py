from datetime import datetime, timedelta
from airflow.decorators import dag
from airflow.sdk import task
import pendulum
from tasks.scraping_job_id_daily import get_job_id
from tasks.scraping_job_detail_daily import each_job_web

from tasks.silver_compony import silver_company_mongodb_to_mysql
from tasks.silver_job_language import silver_job_language
from tasks.silver_job_requirement import silver_job_requirement
from tasks.silver_job_specialty import silver_job_specialty
from tasks.silver_job_skill import silver_job_skill
from tasks.silver_job import silver_job_mongodb_to_mysql
from tasks.silver_job_category import silver_category_mongodb_to_mysql

from tasks.gold_page1 import run_pipeline_page1
from tasks.gold_page2 import run_pipeline_page2
from tasks.gold_page4 import run_pipeline_page4
from tasks.gold_page3 import run_pipeline_page3

from tasks.check_url_status import url_check

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
    dag_id="d_JobTransit_crawler_each_daily",
    default_args=default_args,
    description="An example DAG with Python operators",
    schedule="55 23 * * *",
    start_date=pendulum.datetime(2026, 9, 9, tz="Asia/Taipei"),
    catchup=False,
    tags=["example", "decorator"]  # Optional: Add tags for better filtering in the UI
)
def JobTransit_crawler():

    # 2. @task 放在 DAG 函數內部
    @task
    def run_silver_all_etl():
        silver_company_mongodb_to_mysql()
        silver_job_mongodb_to_mysql()
        silver_category_mongodb_to_mysql()
        silver_job_skill()
        silver_job_specialty()
        silver_job_language()
        silver_job_requirement()

    @task
    def run_gold_all_etl():
        run_pipeline_page1()
        run_pipeline_page2()
        run_pipeline_page4()
        run_pipeline_page3()

    # 3. 呼叫外部/內部的 task 生成 TaskInstance
    t1 = get_job_id()
    t2 = each_job_web()
    t3 = run_silver_all_etl()
    t4 = run_gold_all_etl()
    t5 = url_check()

    # 4. 設定相依性 (Dependency)
    t1 >> t2 >> t3 >> t4 >> t5



# 主執行
JobTransit_crawler()
