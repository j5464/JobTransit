"""104 擷取主流程：Chrome 建立工作階段 → JSON API → 解析 → 儲存。

分層方式延續老師教材：建立 client、逐頁 fetch、逐筆 parse、流式輸出
JSONL/CSV，並在 ``finally`` 關閉外部資源。
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from requests import Session
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait

from .api_client import create_api_session, fetch_job_detail, fetch_search_page
from .api_parser import parse_job_detail_api
from .config import (
    EMPLOYMENT_TYPE_NAME,
    EMPLOYMENT_TYPE_PARAMETER,
    DETAIL_API_URL,
    JOB_CATEGORY_CODE,
    JOB_CATEGORY_NAME,
    SEARCH_API_URL,
    TAIWAN_AREA_CODE,
    TAIWAN_AREA_NAME,
    search_api_url,
    search_page_url,
)
from .errors import AccessBlocked, Crawler104Error, JobPageParseError, JobUnavailable
from .paths import default_raw_root, display_path, raw_locator
from .persistence import MySqlSettings, save_latest_job, sync_jsonl_to_mysql
from .privacy import redact_contact_text, redact_nested
from .quality import QualityAccumulator, save_quality_report
from .storage import (
    StreamingRunWriter,
    append_jsonl,
    iter_jsonl,
    next_available_path,
    rebuild_csv_from_jsonl,
    write_json,
    write_json_snapshot,
)


LOGGER = logging.getLogger(__name__)
TAIPEI = ZoneInfo("Asia/Taipei")
# 只允許 104 目前職缺 ID 使用的英數字，避免 URL 片段成為檔案路徑。
JOB_LINK_PATTERN = re.compile(r"/job/([0-9A-Za-z]{1,64})(?:[/?#]|$)")
SNAPSHOT_TRANSFORM_VERSION = "3.0"


@dataclass(frozen=True)
class CrawlOptions:
    """一次擷取的設定；大型執行以流式輸出控制記憶體用量。"""

    project_root: Path
    raw_root: Path | None = None
    data_root: Path | None = None
    max_jobs: int = 30
    headless: bool = False
    min_delay: float = 3.0
    max_delay: float = 6.0
    timeout: int = 25
    max_search_pages: int = 10
    write_csv: bool = True
    sync_mysql: bool = False
    mysql_batch_size: int = 500
    resume_run_id: str | None = None

    def validate(self) -> None:
        if self.max_jobs < 1:
            raise ValueError("max_jobs 至少為 1")
        if self.min_delay < 3.0:
            raise ValueError("min_delay 至少要 3 秒，以降低對網站的請求負擔")
        if self.max_delay < self.min_delay:
            raise ValueError("max_delay 不可小於 min_delay")
        if self.timeout < 5:
            raise ValueError("timeout 至少要 5 秒")
        if self.max_search_pages < 1:
            raise ValueError("max_search_pages 至少為 1")
        if self.mysql_batch_size < 1:
            raise ValueError("mysql_batch_size 至少為 1")
        if self.resume_run_id is not None and not re.fullmatch(
            r"[0-9A-Za-z+-]+", self.resume_run_id
        ):
            raise ValueError("resume_run_id 含有不安全的路徑字元")


def now_taipei() -> datetime:
    return datetime.now(TAIPEI)


def create_run_id(now: datetime | None = None) -> str:
    """建立 Windows 檔名安全的台北時間 run ID。"""
    current = now or now_taipei()
    return current.strftime("%Y%m%dT%H%M%S%f%z")


def build_search_url(page: int) -> str:
    """建立使用者可在瀏覽器核對的固定搜尋網址。"""
    return search_page_url(page)


def build_search_api_url(page: int) -> str:
    """建立 manifest 使用的目前觀察到的搜尋 JSON 端點 URL。"""
    return search_api_url(page)


def create_driver(*, headless: bool, page_load_timeout: int) -> webdriver.Chrome:
    """建立全新的 Chrome 工作階段，不讀取個人 Chrome profile。"""
    options = ChromeOptions()
    options.add_argument("--lang=zh-TW")
    options.add_argument("--window-size=1440,1200")
    options.add_argument("--disable-notifications")
    if headless:
        options.add_argument("--headless=new")

    # Selenium 4 內建 Selenium Manager，通常不必另外安裝 webdriver-manager。
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(page_load_timeout)
    return driver


def polite_delay(min_seconds: float, max_seconds: float) -> None:
    """用單執行緒間隔降低請求負擔。"""
    seconds = random.uniform(min_seconds, max_seconds)
    LOGGER.info("等待 %.1f 秒後再讀取下一筆", seconds)
    time.sleep(seconds)


def bootstrap_api_session(options: CrawlOptions) -> Session:
    """由目前安裝的 Chrome 取得實際 UA，再建立獨立的 HTTP Session。

    這能避免把教學文章中的 Chrome 81 字串寫死。Chrome 只用全新的暫時
    profile，不讀取使用者登入資料；取得資訊後一定在 ``finally`` 關閉。
    Cookie 不跨 Chrome／requests 搬運，避免不同連線工作階段互相衝突。
    """
    driver: webdriver.Chrome | None = None
    try:
        driver = create_driver(
            headless=options.headless,
            page_load_timeout=options.timeout + 20,
        )
        driver.get(build_search_url(1))
        WebDriverWait(driver, options.timeout).until(
            lambda current: current.execute_script("return document.readyState")
            == "complete"
        )
        user_agent = str(driver.execute_script("return navigator.userAgent"))
        # 保留本機 Chrome 的實際版本，只移除 headless 執行模式字樣。
        user_agent = user_agent.replace("HeadlessChrome", "Chrome")
        LOGGER.info("已由本機 Chrome 建立網頁 JSON HTTP 工作階段")
        return create_api_session(user_agent=user_agent)
    except TimeoutException as error:
        raise Crawler104Error("Chrome 首頁載入逾時，無法建立 API 工作階段") from error
    finally:
        if driver is not None:
            try:
                driver.quit()
                LOGGER.info("Chrome driver 已關閉")
            except WebDriverException as error:
                LOGGER.warning("Chrome driver 關閉時回報錯誤：%s", error)


def _manifest_item(
    *,
    kind: str,
    requested_url: str,
    captured_at: str,
    path: str,
    sha256: str,
    transformation: str,
    source_job_id: str | None = None,
) -> dict[str, Any]:
    """描述一個經 requests 成功取得並保存在本機的 JSON snapshot。"""
    return {
        "kind": kind,
        "source_job_id": source_job_id,
        "requested_url": requested_url,
        "captured_at": captured_at,
        "capture_method": "requests.Session.get",
        "media_type": "application/json",
        "encoding": "utf-8",
        "path": path,
        "sha256": sha256,
        "status": "captured",
        "transformation": transformation,
        "transformation_version": SNAPSHOT_TRANSFORM_VERSION,
    }


def _candidate_from_api(item: Any, *, page: int) -> dict[str, Any] | None:
    """從搜尋 API 單筆資料取得穩定 URL ID；不以職稱＋公司當主鍵。"""
    if not isinstance(item, dict):
        return None
    link = item.get("link")
    job_url = link.get("job") if isinstance(link, dict) else None
    match = JOB_LINK_PATTERN.search(str(job_url or ""))
    if match is None:
        return None
    return {
        "job_id": match.group(1),
        "job_url": f"https://www.104.com.tw/job/{match.group(1)}",
        "title_hint": redact_contact_text(
            str(item.get("jobName") or "（無職稱提示）")
        ),
        "search_page": page,
        "employment_code": item.get("jobRo"),
    }


def _pagination_last_page(payload: dict[str, Any]) -> int | None:
    metadata = payload.get("metadata")
    pagination = metadata.get("pagination") if isinstance(metadata, dict) else None
    last_page = pagination.get("lastPage") if isinstance(pagination, dict) else None
    return last_page if isinstance(last_page, int) else None


def _sanitized_search(payload: dict[str, Any]) -> dict[str, Any]:
    """搜尋 snapshot 只保留研究欄位，排除描述副本與個人化互動狀態。"""
    allowed_fields = (
        "appearDate",
        "coIndustry",
        "coIndustryDesc",
        "custName",
        "custNo",
        "employeeCount",
        "jobAddress",
        "jobAddrNo",
        "jobAddrNoDesc",
        "jobCat",
        "jobName",
        "jobNo",
        "jobRo",
        "jobType",
        "languageRequirements",
        "major",
        "optionEdu",
        "pcSkills",
        "period",
        "remoteWorkType",
        "s10",
        "salaryHigh",
        "salaryLow",
    )
    safe_items: list[dict[str, Any]] = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        safe_item = {key: item[key] for key in allowed_fields if key in item}
        link = item.get("link")
        if isinstance(link, dict):
            safe_item["link"] = {
                key: link[key] for key in ("job", "cust") if key in link
            }
        safe_items.append(safe_item)
    metadata = payload.get("metadata")
    safe_metadata = {}
    if isinstance(metadata, dict):
        safe_metadata = {
            key: metadata[key]
            for key in ("pagination", "filterQuery", "isPreciseHotJob")
            if key in metadata
        }
    return redact_nested({"data": safe_items, "metadata": safe_metadata})


def iter_api_candidates(
    session: Session,
    *,
    options: CrawlOptions,
    raw_run_dir: Path,
    manifest_path: Path,
) -> Iterator[dict[str, Any]]:
    """逐頁 yield 候選，不預設 30+N 上限，直到成功筆數足夠或頁面耗盡。"""
    seen: set[str] = set()
    yielded_any = False

    for page in range(1, options.max_search_pages + 1):
        if page > 1:
            polite_delay(options.min_delay, options.max_delay)
        LOGGER.info("讀取搜尋 API 第 %d 頁", page)
        payload = fetch_search_page(session, page=page)
        captured_at = now_taipei().isoformat(timespec="seconds")
        snapshot_path = next_available_path(
            raw_run_dir / "search" / f"page_{page:03d}.json"
        )
        sha256 = write_json_snapshot(snapshot_path, _sanitized_search(payload))
        snapshot_display = raw_locator(snapshot_path, raw_root=raw_run_dir.parent)
        append_jsonl(
            manifest_path,
            _manifest_item(
                kind="search_api",
                requested_url=build_search_api_url(page),
                captured_at=captured_at,
                path=snapshot_display,
                sha256=sha256,
                transformation="search_field_allowlist_and_recursive_contact_redaction",
            ),
        )

        data = payload["data"]
        if not data:
            if page == 1:
                raise AccessBlocked(
                    "固定篩選搜尋 API 回傳 0 筆，可能是暫時拒絕或工作階段異常。"
                )
            break

        new_on_page = 0
        for item in data:
            candidate = _candidate_from_api(item, page=page)
            if candidate is None or candidate["job_id"] in seen:
                continue
            if candidate["employment_code"] not in (None, 1, "1"):
                continue
            seen.add(candidate["job_id"])
            new_on_page += 1
            yielded_any = True
            yield candidate

        LOGGER.info("第 %d 頁新增 %d 筆不重複候選", page, new_on_page)
        last_page = _pagination_last_page(payload)
        if new_on_page == 0 or (last_page is not None and page >= last_page):
            break

    if not yielded_any:
        raise JobPageParseError("搜尋 API 沒有可辨識的職缺 URL／ID")


def _sanitized_detail(data: dict[str, Any]) -> dict[str, Any]:
    """Raw 詳情只保留研究欄位；未知欄位預設不落地。"""
    section_fields = {
        "header": (
            "jobName",
            "appearDate",
            "custName",
            "custNo",
            "jobType",
        ),
        "jobDetail": (
            "jobDescription",
            "jobCategory",
            "salary",
            "salaryMin",
            "salaryMax",
            "salaryType",
            "jobType",
            "workType",
            "addressNo",
            "addressRegion",
            "addressArea",
            "addressDetail",
            "industryArea",
            "longitude",
            "latitude",
            "manageResp",
            "businessTrip",
            "workPeriod",
            "workPeriodTags",
            "vacationPolicy",
            "startWorkingDay",
            "hireType",
            "delegatedRecruit",
            "needEmp",
            "landmark",
            "remoteWork",
        ),
        "condition": (
            "acceptRole",
            "workExp",
            "edu",
            "major",
            "language",
            "localLanguage",
            "specialty",
            "skill",
            "certificate",
            "driverLicense",
            "other",
        ),
    }
    safe: dict[str, Any] = {
        key: data[key]
        for key in (
            "postalCode",
            "closeDate",
            "industry",
            "industryNo",
            "employees",
            "custNo",
            "chinaCorp",
        )
        if key in data
    }
    for section_name, allowed_fields in section_fields.items():
        section = data.get(section_name)
        if isinstance(section, dict):
            safe[section_name] = {
                key: section[key] for key in allowed_fields if key in section
            }
    return redact_nested(safe)


def _log_error(
    errors_path: Path,
    *,
    phase: str,
    error: Exception,
    url: str,
    job_id: str | None = None,
) -> None:
    append_jsonl(
        errors_path,
        {
            "occurred_at": now_taipei().isoformat(timespec="seconds"),
            "phase": phase,
            "job_id": job_id,
            "url": url,
            "error_type": type(error).__name__,
            "message": str(error),
        },
    )


def crawl(options: CrawlOptions) -> dict[str, Any]:
    """執行一次爬取，無論成功或中止都寫出資料品質與 run summary。"""
    options.validate()
    run_id = options.resume_run_id or create_run_id()
    raw_root = options.raw_root or default_raw_root()
    raw_run_dir = raw_root / run_id
    if options.data_root is None:
        data_root = options.project_root / "data"
        run_output_dir = data_root / "extracted"
    else:
        data_root = options.data_root
        run_output_dir = data_root / "runs" / run_id
        if options.resume_run_id is None:
            try:
                # 原子保留本次 run 目錄；即使極少數 run ID 相撞，也拒絕
                # 啟動，不以 w 模式截斷另一個執行中的歷史輸出。
                run_output_dir.mkdir(parents=True, exist_ok=False)
            except FileExistsError as error:
                raise ValueError(f"run ID 已存在，拒絕覆寫：{run_id}") from error
    latest_root = data_root / "latest" / "jobs"
    processed_dir = options.project_root / "data" / "processed"
    manifest_path = raw_run_dir / "manifest.jsonl"
    errors_path = raw_run_dir / "errors.jsonl"

    record_count = 0
    latest_written_count = 0
    quality_accumulator = QualityAccumulator()
    status = "completed"
    stop_reason: str | None = None
    session: Session | None = None
    output_writer = StreamingRunWriter(
        run_output_dir,
        run_id=run_id,
        write_csv=options.write_csv,
        append_existing=options.resume_run_id is not None,
    )
    completed_job_ids: set[str] = set()
    if options.resume_run_id is not None:
        jsonl_path = output_writer.paths["jsonl"]
        csv_path = run_output_dir / f"jobs_{run_id}.csv"
        if not jsonl_path.is_file():
            raise ValueError(f"找不到要續跑的 run JSONL：{jsonl_path}")
        if not options.write_csv and csv_path.is_file():
            raise ValueError(
                "既有 run 已包含 CSV；續跑不可加 --no-csv，以免 JSONL/CSV 筆數不一致"
            )
        if (
            options.write_csv
            and jsonl_path.stat().st_size > 0
            and not csv_path.is_file()
        ):
            raise ValueError("續跑的 CSV 不存在；請改用 --no-csv 或先還原該 CSV")
        if options.write_csv and csv_path.is_file():
            # JSONL 是 durable spool；每次續跑前原子重建衍生 CSV，修復
            # JSONL flush 後、CSV 寫入前中斷所造成的列數差異。
            rebuild_csv_from_jsonl(jsonl_path, csv_path)
        for previous_record in iter_jsonl(jsonl_path):
            source = previous_record.get("source")
            previous_job_id = (
                str(source.get("job_id")) if isinstance(source, dict) else ""
            )
            if previous_job_id:
                completed_job_ids.add(previous_job_id)
            # run JSONL 是可重播的 durable spool；latest 遺失或損壞時，
            # 續跑會先由既有 canonical record 修復，不假設檔案一定存在。
            save_latest_job(previous_record, root=latest_root)
            latest_written_count += 1
            quality_accumulator.add(previous_record)
            record_count += 1

    LOGGER.info(
        "開始爬取：職類=%s、工作性質=%s、地區=%s、目標=%d 筆",
        JOB_CATEGORY_NAME,
        EMPLOYMENT_TYPE_NAME,
        TAIWAN_AREA_NAME,
        options.max_jobs,
    )
    LOGGER.info("Raw snapshots 使用 raw-root:// locator；實際根目錄由 CLI 設定")
    with output_writer:
        try:
            consecutive_transport_failures = 0
            if record_count < options.max_jobs:
                session = bootstrap_api_session(options)
            candidates = (
                iter_api_candidates(
                    session,
                    options=options,
                    raw_run_dir=raw_run_dir,
                    manifest_path=manifest_path,
                )
                if session is not None
                else iter(())
            )
            for candidate in candidates:
                if record_count >= options.max_jobs:
                    break
                if candidate["job_id"] in completed_job_ids:
                    continue
                polite_delay(options.min_delay, options.max_delay)
                job_id = candidate["job_id"]
                job_url = candidate["job_url"]
                requested_url = DETAIL_API_URL.format(job_id=job_id)
                LOGGER.info(
                    "擷取詳情 %d/%d：%s (%s)",
                    record_count + 1,
                    options.max_jobs,
                    candidate["title_hint"],
                    job_id,
                )
                try:
                    detail = fetch_job_detail(session, job_id=job_id)
                    safe_detail = _sanitized_detail(detail)
                    scraped_at = now_taipei().isoformat(timespec="seconds")
                    snapshot_path = next_available_path(
                        raw_run_dir / "detail" / f"{job_id}.json"
                    )
                    snapshot_display = raw_locator(snapshot_path, raw_root=raw_root)
                    record = parse_job_detail_api(
                        safe_detail,
                        job_id=job_id,
                        requested_url=requested_url,
                        run_id=run_id,
                        search_page=candidate["search_page"],
                        scraped_at=scraped_at,
                        raw_payload_path=snapshot_display,
                        raw_sha256=None,
                    )
                    employment_type = record["job"].get("employment_type_raw")
                    if employment_type != EMPLOYMENT_TYPE_NAME:
                        raise JobPageParseError(
                            f"職缺 {job_id} 的工作性質不是全職：{employment_type}"
                        )

                    # 必要欄位與全職條件都通過後，依序保存 Raw、latest、run spool。
                    sha256 = write_json_snapshot(snapshot_path, safe_detail)
                    record["source"]["raw_sha256"] = sha256
                    append_jsonl(
                        manifest_path,
                        _manifest_item(
                            kind="detail_api",
                            source_job_id=job_id,
                            requested_url=requested_url,
                            captured_at=scraped_at,
                            path=snapshot_display,
                            sha256=sha256,
                            transformation=(
                                "detail_field_allowlist_and_recursive_contact_redaction"
                            ),
                        ),
                    )
                    save_latest_job(record, root=latest_root)
                    latest_written_count += 1
                    output_writer.append(record)
                    quality_accumulator.add(record)
                    completed_job_ids.add(job_id)
                    record_count += 1
                    consecutive_transport_failures = 0
                    LOGGER.info("完成 %d/%d 筆", record_count, options.max_jobs)
                    if record_count >= options.max_jobs:
                        break
                except AccessBlocked as error:
                    _log_error(
                        errors_path,
                        phase="detail_api",
                        error=error,
                        url=requested_url,
                        job_id=job_id,
                    )
                    status = "blocked"
                    stop_reason = str(error)
                    LOGGER.error("API 拒絕存取，立即停止：%s", error)
                    break
                except JobPageParseError as error:
                    _log_error(
                        errors_path,
                        phase="detail_parse",
                        error=error,
                        url=job_url,
                        job_id=job_id,
                    )
                    consecutive_transport_failures = 0
                    LOGGER.warning("略過無法解析的職缺 %s：%s", job_id, error)
                except JobUnavailable as error:
                    _log_error(
                        errors_path,
                        phase="detail_unavailable",
                        error=error,
                        url=requested_url,
                        job_id=job_id,
                    )
                    consecutive_transport_failures = 0
                    LOGGER.info("略過已關閉或不存在的職缺 %s：%s", job_id, error)
                except Crawler104Error as error:
                    _log_error(
                        errors_path,
                        phase="detail_api",
                        error=error,
                        url=requested_url,
                        job_id=job_id,
                    )
                    consecutive_transport_failures += 1
                    LOGGER.warning("職缺 %s 暫時取得失敗：%s", job_id, error)
                    if consecutive_transport_failures >= 3:
                        status = "failed"
                        stop_reason = (
                            "連續 3 個詳情 API 傳輸或格式失敗，停止本次執行。"
                        )
                        break
        except AccessBlocked as error:
            status = "blocked"
            stop_reason = str(error)
            _log_error(errors_path, phase="search_api", error=error, url=SEARCH_API_URL)
            LOGGER.error("API 拒絕存取，立即停止：%s", error)
        except (Crawler104Error, JobPageParseError, WebDriverException) as error:
            status = "failed"
            stop_reason = str(error)
            _log_error(
                errors_path,
                phase="startup_or_search",
                error=error,
                url=SEARCH_API_URL,
            )
            LOGGER.error("擷取流程停止：%s", error)
        except (OSError, ValueError) as error:
            status = "failed"
            stop_reason = f"儲存資料失敗：{error}"
            _log_error(
                errors_path,
                phase="persistence",
                error=error,
                url=None,
            )
            LOGGER.error("儲存流程停止：%s", error)
        except KeyboardInterrupt:
            status = "interrupted"
            stop_reason = "使用者中斷執行；已完成資料可用 --resume-run 續跑。"
            LOGGER.warning(stop_reason)
        finally:
            if session is not None:
                session.close()
                LOGGER.info("HTTP session 已關閉")

    if record_count < options.max_jobs and status == "completed":
        status = "partial"
        stop_reason = f"搜尋頁耗盡，只取得 {record_count}/{options.max_jobs} 筆。"

    output_paths = output_writer.paths
    quality_report = quality_accumulator.build(expected_count=options.max_jobs)
    quality_path = processed_dir / f"quality_report_{run_id}.json"
    save_quality_report(quality_report, quality_path)

    mysql_status = "not_requested"
    mysql_upserted_count = 0
    mysql_error: str | None = None
    if options.sync_mysql and status != "interrupted":
        try:
            mysql_status = "running"
            mysql_upserted_count = sync_jsonl_to_mysql(
                output_paths["jsonl"],
                settings=MySqlSettings.from_env(),
                batch_size=options.mysql_batch_size,
            )
            mysql_status = "completed"
        except KeyboardInterrupt:
            mysql_status = "interrupted"
            status = "interrupted"
            stop_reason = "使用者中斷 MySQL 同步；run JSONL 可稍後重新同步。"
            LOGGER.warning(stop_reason)
        except Exception as error:
            mysql_status = "failed"
            mysql_error = str(error)
            LOGGER.error("MySQL 同步失敗；run JSONL 可稍後重播：%s", error)
            if status in {"completed", "partial"}:
                status = "failed"
                stop_reason = "爬取檔案已保存，但 MySQL 同步失敗；可稍後重播 JSONL。"
    elif options.sync_mysql:
        mysql_status = "skipped_interrupted"

    summary = {
        "run_id": run_id,
        "status": status,
        "stop_reason": stop_reason,
        "target_count": options.max_jobs,
        "record_count": record_count,
        "latest_written_count": latest_written_count,
        "mysql_sync": {
            "enabled": options.sync_mysql,
            "status": mysql_status,
            "upserted_count": mysql_upserted_count,
            "error": mysql_error,
        },
        "transport": "104_current_undocumented_web_json_endpoint",
        "snapshot_transformation_version": SNAPSHOT_TRANSFORM_VERSION,
        "query": {
            "area": TAIWAN_AREA_NAME,
            "area_code": TAIWAN_AREA_CODE,
            "jobcat_name": JOB_CATEGORY_NAME,
            "jobcat_code": JOB_CATEGORY_CODE,
            "employment_type": EMPLOYMENT_TYPE_NAME,
            "employment_type_parameter": EMPLOYMENT_TYPE_PARAMETER,
        },
        "outputs": {
            # 結構化輸出不保存 C:\Users\<帳號>，只保留可攜式 locator。
            "raw_root": "raw-root://",
            "data_root": display_path(data_root, root=options.project_root),
            "latest_root": display_path(latest_root, root=options.project_root),
            "jsonl": display_path(output_paths["jsonl"], root=options.project_root),
            "csv": (
                display_path(output_paths["csv"], root=options.project_root)
                if "csv" in output_paths
                else None
            ),
            "quality_report": display_path(quality_path, root=options.project_root),
            "manifest": (
                raw_locator(manifest_path, raw_root=raw_root)
                if manifest_path.exists()
                else None
            ),
            "errors": (
                raw_locator(errors_path, raw_root=raw_root)
                if errors_path.exists()
                else None
            ),
        },
    }
    summary_path = processed_dir / f"run_summary_{run_id}.json"
    summary["outputs"]["run_summary"] = display_path(
        summary_path, root=options.project_root
    )
    write_json(summary_path, summary)
    return summary
