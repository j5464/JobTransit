"""104 目前可觀察到的免登入職缺 JSON 端點用戶端。

老師教材的 requests 寫法在此保留：共用 Session、HTTPAdapter + Retry、
連線／讀取 timeout、raise_for_status，以及依錯誤類型提供清楚訊息。
"""

from __future__ import annotations

import random
import time
from typing import Any

import requests
from requests import Response, Session
from requests.adapters import HTTPAdapter
from requests.exceptions import HTTPError, RequestException, Timeout
from urllib3.util.retry import Retry

from .config import (
    DETAIL_API_URL,
    SEARCH_API_URL,
    search_page_url,
    search_parameters,
)
from .errors import AccessBlocked, ApiPayloadError, Crawler104Error, JobUnavailable


class MinimumDelayRetry(Retry):
    """讓 adapter 的暫時性 5xx retry 也至少等待 3 秒。"""

    def sleep(self, response: Any = None) -> None:
        retry_after = self.get_retry_after(response) if response is not None else None
        base_wait = max(3.0, float(retry_after or 0), self.get_backoff_time())
        time.sleep(base_wait + random.uniform(0, 3))


def create_api_session(*, user_agent: str) -> Session:
    """建立可重用的 Session，沿用目前 Chrome 版本相符的 User-Agent。"""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        }
    )

    # 只重試暫時性的伺服器錯誤；403/429 不重試，交由上層立即停止。
    retry = MinimumDelayRetry(
        total=3,
        backoff_factor=1,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
        # 避免 urllib3 因 429 的 Retry-After 自動重試；交給上層立即停止。
        respect_retry_after_header=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


def _response_json(
    response: Response,
    *,
    context: str,
    unavailable_statuses: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    """統一處理拒絕狀態、HTTP 錯誤與 JSON 格式錯誤。"""
    if response.status_code in {403, 429}:
        raise AccessBlocked(
            f"{context} 收到 HTTP {response.status_code}，停止本次擷取。"
        )
    if response.status_code in unavailable_statuses:
        raise JobUnavailable(
            f"{context} 收到 HTTP {response.status_code}，職缺可能已關閉。"
        )
    try:
        response.raise_for_status()
    except HTTPError as error:
        raise Crawler104Error(
            f"{context} HTTP 錯誤：{response.status_code}"
        ) from error

    try:
        payload = response.json()
    except requests.JSONDecodeError as error:
        raise ApiPayloadError(f"{context} 回應不是合法 JSON") from error
    if not isinstance(payload, dict):
        raise ApiPayloadError(f"{context} JSON 根節點不是物件")
    return payload


def _get_json(
    session: Session,
    url: str,
    *,
    referer: str,
    params: dict[str, Any] | None = None,
    context: str,
    unavailable_statuses: frozenset[int] = frozenset(),
) -> dict[str, Any]:
    """執行一次有連線與讀取上限的 GET。"""
    try:
        response = session.get(
            url,
            params=params,
            headers={"Referer": referer},
            timeout=(5, 20),
        )
    except Timeout as error:
        raise Crawler104Error(f"{context} 逾時") from error
    except RequestException as error:
        raise Crawler104Error(f"{context} 連線失敗：{error}") from error
    return _response_json(
        response,
        context=context,
        unavailable_statuses=unavailable_statuses,
    )


def fetch_search_page(session: Session, *, page: int) -> dict[str, Any]:
    """取得固定篩選條件的一頁候選職缺 JSON。"""
    referer = search_page_url(page)
    payload = _get_json(
        session,
        SEARCH_API_URL,
        referer=referer,
        params=search_parameters(page),
        context=f"搜尋 API 第 {page} 頁",
    )
    if not isinstance(payload.get("data"), list):
        raise ApiPayloadError("搜尋 API 缺少 data 清單")
    return payload


def fetch_job_detail(session: Session, *, job_id: str) -> dict[str, Any]:
    """取得一筆職缺詳情；回傳 API 的 `data` 物件。"""
    job_url = f"https://www.104.com.tw/job/{job_id}"
    payload = _get_json(
        session,
        DETAIL_API_URL.format(job_id=job_id),
        referer=job_url,
        context=f"職缺 {job_id} 詳情 API",
        unavailable_statuses=frozenset({404, 410}),
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ApiPayloadError(f"職缺 {job_id} 詳情 API 缺少 data 物件")
    return data
