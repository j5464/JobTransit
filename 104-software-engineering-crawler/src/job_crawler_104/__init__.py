"""104 職缺爬蟲教學專案的穩定公開介面。"""

from .api_parser import parse_job_detail_api
from .crawler import CrawlOptions, crawl
from .parser import parse_job_detail, parse_search_page
from .persistence import (
    MySqlSettings,
    save_latest_job,
    sync_jsonl_to_mysql,
    upsert_latest_jobs,
)

__all__ = [
    "CrawlOptions",
    "crawl",
    "parse_job_detail_api",
    "parse_job_detail",
    "parse_search_page",
    "MySqlSettings",
    "save_latest_job",
    "sync_jsonl_to_mysql",
    "upsert_latest_jobs",
]
