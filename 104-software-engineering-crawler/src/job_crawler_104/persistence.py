"""最新職缺檔案與 MySQL 儲存介面。

Raw snapshot 仍由 :mod:`crawler` 依 run 保存；本模組只管理可覆寫的最新版本。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


SAFE_JOB_ID = re.compile(r"^[0-9A-Za-z]{1,64}$")

MYSQL_COLUMNS = (
    "job_id",
    "schema_version",
    "latest_run_id",
    "source_name",
    "query_jobcat_code",
    "query_jobcat_name",
    "query_employment_type",
    "query_area",
    "search_page_number",
    "job_url",
    "display_date_raw",
    "job_title",
    "company_id",
    "company_name",
    "employment_type_raw",
    "job_categories",
    "location_raw",
    "address_raw",
    "salary_raw",
    "job_description",
    "requirements_text",
    "experience_raw",
    "education_raw",
    "majors",
    "languages",
    "tools",
    "skills",
    "other_requirements",
    "quality_status",
    "quality_warnings",
    "raw_payload_path",
    "raw_sha256",
    "content_sha256",
    "canonical_json",
    "first_seen_at",
    "last_seen_at",
)

_MYSQL_GUARDED_COLUMNS = tuple(
    column
    for column in MYSQL_COLUMNS
    if column not in {"job_id", "first_seen_at", "last_seen_at"}
)
_MYSQL_INSERT_COLUMNS = ", ".join(f"`{column}`" for column in MYSQL_COLUMNS)
_MYSQL_PLACEHOLDERS = ", ".join(["%s"] * len(MYSQL_COLUMNS))
_MYSQL_GUARDED_UPDATES = ",\n  ".join(
    f"`{column}` = IF(incoming.last_seen_at >= jobs.last_seen_at, "
    f"incoming.`{column}`, jobs.`{column}`)"
    for column in _MYSQL_GUARDED_COLUMNS
)
MYSQL_UPSERT_SQL = (
    f"INSERT INTO `jobs` ({_MYSQL_INSERT_COLUMNS})\n"
    f"VALUES ({_MYSQL_PLACEHOLDERS}) AS incoming\n"
    "ON DUPLICATE KEY UPDATE\n  "
    f"{_MYSQL_GUARDED_UPDATES},\n"
    "  `first_seen_at` = LEAST(jobs.first_seen_at, incoming.first_seen_at),\n"
    "  `last_seen_at` = GREATEST(jobs.last_seen_at, incoming.last_seen_at)"
)
MYSQL_SCHEMA_CHECK_SQL = (
    "SELECT " + ", ".join(f"`{column}`" for column in MYSQL_COLUMNS) + " "
    "FROM `jobs` LIMIT 0"
)


@dataclass(frozen=True)
class MySqlSettings:
    """MySQL 連線設定；密碼不出現在 repr 或程式預設值。"""

    host: str = "127.0.0.1"
    port: int = 3306
    database: str = "job_crawler_104"
    user: str = "root"
    password: str = field(default="", repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "MySqlSettings":
        values = os.environ if env is None else env
        password = values.get("JOB104_MYSQL_PASSWORD")
        if password is None:
            raise ValueError(
                "啟用 MySQL 前請先設定 JOB104_MYSQL_PASSWORD 環境變數"
            )
        try:
            port = int(values.get("JOB104_MYSQL_PORT", "3306"))
        except ValueError as error:
            raise ValueError("JOB104_MYSQL_PORT 必須是整數") from error
        if not 1 <= port <= 65535:
            raise ValueError("JOB104_MYSQL_PORT 必須介於 1 與 65535")
        return cls(
            host=values.get("JOB104_MYSQL_HOST", "127.0.0.1"),
            port=port,
            database=values.get("JOB104_MYSQL_DATABASE", "job_crawler_104"),
            user=values.get("JOB104_MYSQL_USER", "root"),
            password=password,
        )


def _job_id(record: dict[str, Any]) -> str:
    source = record.get("source")
    value = source.get("job_id") if isinstance(source, dict) else None
    job_id = str(value or "")
    if not SAFE_JOB_ID.fullmatch(job_id):
        raise ValueError(f"不安全或缺漏的 job_id：{job_id!r}")
    return job_id


def job_content_hash(record: dict[str, Any]) -> str:
    """計算排除 run 時間與 Raw 路徑後的穩定職缺內容雜湊。"""

    content = {
        "schema_version": record.get("schema_version"),
        "job_id": _job_id(record),
        "job": record.get("job"),
        "company": record.get("company"),
        "location": record.get("location"),
        "salary": record.get("salary"),
        "requirements": record.get("requirements"),
        "sections": record.get("sections"),
    }
    serialized = json.dumps(
        content,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _scraped_at(record: dict[str, Any]) -> datetime:
    run = record.get("run")
    value = run.get("scraped_at") if isinstance(run, dict) else None
    if not isinstance(value, str):
        raise ValueError("record.run.scraped_at 必須是 RFC 3339 字串")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"無法解析 scraped_at：{value!r}") from error
    if parsed.tzinfo is None:
        raise ValueError("record.run.scraped_at 必須包含時區")
    return parsed


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _json_text(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def record_to_mysql_values(
    record: dict[str, Any],
    *,
    first_seen_at: datetime | None = None,
) -> tuple[Any, ...]:
    """將 canonical record 映射成 ``jobs`` 資料表的一列。"""

    run = _mapping(record.get("run"))
    query = _mapping(run.get("query"))
    source = _mapping(record.get("source"))
    job = _mapping(record.get("job"))
    description = _mapping(job.get("description"))
    company = _mapping(record.get("company"))
    location = _mapping(record.get("location"))
    salary = _mapping(record.get("salary"))
    requirements = _mapping(record.get("requirements"))
    quality = _mapping(record.get("quality"))
    captured_at = _scraped_at(record)
    earliest_at = first_seen_at or captured_at
    if earliest_at.tzinfo is None:
        raise ValueError("first_seen_at 必須包含時區")
    first_seen_value = earliest_at.astimezone(timezone.utc).replace(tzinfo=None)
    last_seen_value = captured_at.astimezone(timezone.utc).replace(tzinfo=None)

    values_by_column: dict[str, Any] = {
        "job_id": _job_id(record),
        "schema_version": record.get("schema_version"),
        "latest_run_id": run.get("run_id"),
        "source_name": source.get("name"),
        "query_jobcat_code": query.get("jobcat_code"),
        "query_jobcat_name": query.get("jobcat_name"),
        "query_employment_type": query.get("employment_type"),
        "query_area": query.get("area"),
        "search_page_number": query.get("search_page"),
        "job_url": source.get("job_url"),
        "display_date_raw": source.get("display_date_raw"),
        "job_title": job.get("title"),
        "company_id": company.get("id"),
        "company_name": company.get("name"),
        "employment_type_raw": job.get("employment_type_raw"),
        "job_categories": _json_text(job.get("categories", [])),
        "location_raw": location.get("raw"),
        "address_raw": location.get("address_raw"),
        "salary_raw": salary.get("raw"),
        "job_description": description.get("text"),
        "requirements_text": requirements.get("text"),
        "experience_raw": requirements.get("experience_raw"),
        "education_raw": requirements.get("education_raw"),
        "majors": _json_text(requirements.get("majors", [])),
        "languages": _json_text(requirements.get("languages", [])),
        "tools": _json_text(requirements.get("tools", [])),
        "skills": _json_text(requirements.get("skills", [])),
        "other_requirements": requirements.get("other_text"),
        "quality_status": quality.get("status"),
        "quality_warnings": _json_text(quality.get("warnings", [])),
        "raw_payload_path": source.get("raw_payload_path"),
        "raw_sha256": source.get("raw_sha256"),
        "content_sha256": job_content_hash(record),
        "canonical_json": _json_text(record),
        "first_seen_at": first_seen_value,
        "last_seen_at": last_seen_value,
    }
    return tuple(values_by_column[column] for column in MYSQL_COLUMNS)


def upsert_latest_jobs(connection: Any, records: Iterable[dict[str, Any]]) -> int:
    """在一個 transaction 中批次更新最新職缺；失敗時完整 rollback。"""

    deduplicated: dict[str, tuple[dict[str, Any], datetime]] = {}
    for record in records:
        job_id = _job_id(record)
        observed_at = _scraped_at(record)
        previous = deduplicated.get(job_id)
        if previous is None:
            deduplicated[job_id] = (record, observed_at)
            continue
        latest_record, earliest_at = previous
        if observed_at >= _scraped_at(latest_record):
            latest_record = record
        deduplicated[job_id] = (latest_record, min(earliest_at, observed_at))
    if not deduplicated:
        return 0

    rows = [
        record_to_mysql_values(record, first_seen_at=earliest_at)
        for record, earliest_at in deduplicated.values()
    ]
    try:
        with connection.cursor() as cursor:
            cursor.executemany(MYSQL_UPSERT_SQL, rows)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return len(rows)


def connect_mysql(settings: MySqlSettings) -> Any:
    """延遲載入 PyMySQL，且只連線既有 schema、不執行 DDL。"""

    import pymysql

    return pymysql.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        database=settings.database,
        charset="utf8mb4",
        autocommit=False,
        init_command="SET time_zone = '+00:00'",
        connect_timeout=10,
        read_timeout=30,
        write_timeout=60,
    )


def verify_mysql_schema(connection: Any) -> None:
    """以唯讀查詢確認 Workbench 已建立相容的 ``jobs`` 表。"""

    with connection.cursor() as cursor:
        cursor.execute(MYSQL_SCHEMA_CHECK_SQL)


def sync_jsonl_to_mysql(
    jsonl_path: Path,
    *,
    settings: MySqlSettings,
    batch_size: int = 500,
    connection_factory: Callable[[MySqlSettings], Any] | None = None,
) -> int:
    """串流讀取一份 run JSONL，分批冪等同步到 MySQL 最新資料表。"""

    if batch_size < 1:
        raise ValueError("batch_size 至少為 1")
    factory = connection_factory or connect_mysql
    connection = factory(settings)
    synced = 0
    batch: list[dict[str, Any]] = []
    try:
        verify_mysql_schema(connection)
        with jsonl_path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as error:
                    raise ValueError(
                        f"{jsonl_path} 第 {line_number} 列不是合法 JSON"
                    ) from error
                if not isinstance(record, dict):
                    raise ValueError(f"{jsonl_path} 第 {line_number} 列不是 JSON 物件")
                batch.append(record)
                if len(batch) >= batch_size:
                    synced += upsert_latest_jobs(connection, batch)
                    batch.clear()
        if batch:
            synced += upsert_latest_jobs(connection, batch)
    finally:
        connection.close()
    return synced


def save_latest_job(record: dict[str, Any], *, root: Path) -> Path:
    """以 ``job_id`` 分片並原子覆寫一份最新 canonical JSON。"""

    job_id = _job_id(record)
    target = root / job_id[:2].lower() / f"{job_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    incoming_time = _scraped_at(record)
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
            if _scraped_at(existing) > incoming_time:
                return target
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            # 既有 latest 無法驗證時，以這筆通過 parser 的 canonical record 修復。
            pass
    text = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{job_id}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        ) as temporary:
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, target)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target
