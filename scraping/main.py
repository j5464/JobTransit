from scraping_job_id import get_job_id
from job_detail import each_job_web
from export_to_json import save_jobs_to_json

def main():
    get_job_id()
    each_job_web()


if __name__ == "__main__":
    main()
