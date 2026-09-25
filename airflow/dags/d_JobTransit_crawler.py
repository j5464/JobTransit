from datetime import datetime, timedelta
from airflow.sdk import dag, task
from tasks.scraping_job_id import get_job_id
from tasks.scraping_job_detail_daily import each_job_web

from tasks.silver_compony import silver_company_mongodb_to_mysql
from tasks.silver_job_language import silver_job_language
from tasks.silver_job_requirement import silver_job_requirement
from tasks.silver_job_specialty import silver_job_specialty
from tasks.silver_job_skill import silver_job_skill
from tasks.silver_job import silver_job_mongodb_to_mysql
from tasks.silver_job_category import silver_category_mongodb_to_mysql

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
    dag_id="d_JobTransit_crawler",
    default_args=default_args,
    description="An example DAG with Python operators",
    schedule="* 10 10 12 *",
    start_date=datetime(2026, 9, 1),
    catchup=False,
    tags=["example", "decorator"]  # Optional: Add tags for better filtering in the UI
)
def JobTransit_crawler():

    # 2. @task 放在 DAG 函數內部
    @task
    def run_silver_all_etl():
        silver_company_mongodb_to_mysql(filter_by_date= False)
        silver_job_mongodb_to_mysql(filter_by_date= False)
        silver_category_mongodb_to_mysql(filter_by_date= False)
        silver_job_skill(filter_by_date= False)
        silver_job_specialty(filter_by_date= False)
        silver_job_language(filter_by_date= False)
        silver_job_requirement(filter_by_date= False)

    # 3. 呼叫外部/內部的 task 生成 TaskInstance
    t1 = get_job_id()
    t2 = each_job_web()
    t3 = run_silver_all_etl()
    t4 = url_check()

    # 4. 設定相依性 (Dependency)
    t1 >> t2 >> t3 >> t4

# 主執行
JobTransit_crawler()
