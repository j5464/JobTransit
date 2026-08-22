"""本專題固定的搜尋範圍，集中管理以避免各模組出現不同條件。"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode


SOURCE_NAME = "104"
CANONICAL_SCHEMA_VERSION = "2.0"
SEARCH_BASE_URL = "https://www.104.com.tw/jobs/search/"
SEARCH_API_URL = "https://www.104.com.tw/jobs/search/api/jobs"
DETAIL_API_URL = "https://www.104.com.tw/api/jobs/{job_id}"

JOB_CATEGORY_CODE = "2007001000"
JOB_CATEGORY_NAME = "軟體／工程類人員"
TAIWAN_AREA_CODE = "6001000000"
TAIWAN_AREA_NAME = "台灣地區"
EMPLOYMENT_TYPE_NAME = "全職"
EMPLOYMENT_TYPE_PARAMETER = "ro=1"


def search_parameters(page: int) -> dict[str, str | int]:
    """搜尋頁與 JSON endpoint 共用的單一查詢條件來源。"""
    return {
        "area": TAIWAN_AREA_CODE,
        "jobcat": JOB_CATEGORY_CODE,
        "ro": "1",
        "page": page,
        "jobsource": "joblist_search",
    }


def search_page_url(page: int) -> str:
    params = {**search_parameters(page), "searchJobs": "1"}
    return f"{SEARCH_BASE_URL}?{urlencode(params)}"


def search_api_url(page: int) -> str:
    return f"{SEARCH_API_URL}?{urlencode(search_parameters(page))}"


def query_metadata(search_page: int) -> dict[str, Any]:
    """建立寫入每筆職缺的查詢來源資訊。"""
    return {
        "jobcat_code": JOB_CATEGORY_CODE,
        "jobcat_name": JOB_CATEGORY_NAME,
        "employment_type": EMPLOYMENT_TYPE_NAME,
        "area": TAIWAN_AREA_NAME,
        "search_page": search_page,
    }
