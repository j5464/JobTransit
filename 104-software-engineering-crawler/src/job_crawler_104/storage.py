"""Raw JSON snapshot、manifest、canonical JSONL 與 CSV 儲存功能。"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from types import TracebackType
from typing import Any, Iterable, Iterator


CSV_COLUMNS = [
    "schema_version",
    "run_id",
    "source",
    "query_jobcat_code",
    "query_jobcat_name",
    "query_employment_type",
    "query_area",
    "search_page_number",
    "source_job_id",
    "job_url",
    "scraped_at",
    "display_date_raw",
    "raw_html_path",
    "html_sha256",
    "raw_payload_path",
    "raw_sha256",
    "parse_status",
    "parse_warnings_json",
    "job_title",
    "company_id",
    "company_name",
    "employment_type_raw",
    "job_categories_json",
    "location_raw",
    "address_raw",
    "salary_raw",
    "job_description_text",
    "requirements_text",
    "job_description_items_json",
    "experience_raw",
    "education_raw",
    "majors_json",
    "languages_json",
    "tools_json",
    "skills_json",
    "other_requirements_text",
    "requirements_kv_json",
    "sections_json",
]


def _json_text(value: Any) -> str:
    """CSV 的巢狀欄位使用合法 JSON，不使用 Python repr。"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _csv_safe(value: Any) -> Any:
    """避免使用 Excel 開 CSV 時把網頁文字誤當成公式執行。

    Canonical JSONL 不套用 Excel 轉義；只有面向試算表的 CSV 會在
    危險開頭前加單引號。
    """
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    """將 canonical record 投影成一職缺一列的分析用 CSV schema。"""
    run = record["run"]
    query = run["query"]
    source = record["source"]
    job = record["job"]
    company = record["company"]
    requirements = record["requirements"]
    quality = record["quality"]

    row = {
        "schema_version": record["schema_version"],
        "run_id": run["run_id"],
        "source": source["name"],
        "query_jobcat_code": query["jobcat_code"],
        "query_jobcat_name": query["jobcat_name"],
        "query_employment_type": query["employment_type"],
        "query_area": query["area"],
        "search_page_number": query["search_page"],
        "source_job_id": str(source["job_id"]),
        "job_url": source["job_url"],
        "scraped_at": run["scraped_at"],
        "display_date_raw": source.get("display_date_raw"),
        "raw_html_path": source.get("raw_html_path"),
        "html_sha256": source.get("html_sha256"),
        "raw_payload_path": source.get("raw_payload_path"),
        "raw_sha256": source.get("raw_sha256"),
        "parse_status": quality["status"],
        "parse_warnings_json": _json_text(quality["warnings"]),
        "job_title": job["title"],
        "company_id": (
            str(company["id"]) if company.get("id") is not None else None
        ),
        "company_name": company["name"],
        "employment_type_raw": job.get("employment_type_raw"),
        "job_categories_json": _json_text(job.get("categories", [])),
        "location_raw": record["location"].get("raw"),
        "address_raw": record["location"].get("address_raw"),
        "salary_raw": record["salary"].get("raw"),
        "job_description_text": job["description"].get("text"),
        "requirements_text": requirements.get("text"),
        "job_description_items_json": _json_text(
            job["description"].get("items", [])
        ),
        "experience_raw": requirements.get("experience_raw"),
        "education_raw": requirements.get("education_raw"),
        "majors_json": _json_text(requirements.get("majors", [])),
        "languages_json": _json_text(requirements.get("languages", [])),
        "tools_json": _json_text(requirements.get("tools", [])),
        "skills_json": _json_text(requirements.get("skills", [])),
        "other_requirements_text": requirements.get("other_text"),
        "requirements_kv_json": _json_text(requirements.get("key_values", [])),
        "sections_json": _json_text(record.get("sections", [])),
    }
    return {key: _csv_safe(value) for key, value in row.items()}


class StreamingRunWriter:
    """逐筆寫入 run JSONL／CSV，避免將上萬筆資料同時放進記憶體。"""

    def __init__(
        self,
        output_dir: Path,
        *,
        run_id: str,
        write_csv: bool = True,
        append_existing: bool = False,
    ) -> None:
        self.output_dir = output_dir
        self.run_id = run_id
        self.write_csv = write_csv
        self.append_existing = append_existing
        self.paths: dict[str, Path] = {
            "jsonl": output_dir / f"jobs_{run_id}.jsonl"
        }
        if write_csv:
            self.paths["csv"] = output_dir / f"jobs_{run_id}.csv"
        self._jsonl_file: Any = None
        self._csv_file: Any = None
        self._csv_writer: csv.DictWriter | None = None

    def __enter__(self) -> "StreamingRunWriter":
        self.output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_mode = "a" if self.append_existing else "w"
        try:
            self._jsonl_file = self.paths["jsonl"].open(
                jsonl_mode, encoding="utf-8", newline="\n"
            )
            if self.write_csv:
                csv_path = self.paths["csv"]
                csv_has_content = (
                    self.append_existing
                    and csv_path.exists()
                    and csv_path.stat().st_size > 0
                )
                csv_mode = "a" if self.append_existing else "w"
                csv_encoding = "utf-8" if csv_has_content else "utf-8-sig"
                self._csv_file = self.paths["csv"].open(
                    csv_mode, encoding=csv_encoding, newline=""
                )
                self._csv_writer = csv.DictWriter(
                    self._csv_file,
                    fieldnames=CSV_COLUMNS,
                    extrasaction="ignore",
                )
                if not csv_has_content:
                    self._csv_writer.writeheader()
                    self._csv_file.flush()
        except BaseException:
            if self._csv_file is not None:
                self._csv_file.close()
            if self._jsonl_file is not None:
                self._jsonl_file.close()
            raise
        return self

    def append(self, record: dict[str, Any]) -> None:
        if self._jsonl_file is None:
            raise RuntimeError("StreamingRunWriter 必須先進入 with 區塊")
        self._jsonl_file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._jsonl_file.flush()
        if self._csv_writer is not None and self._csv_file is not None:
            self._csv_writer.writerow(flatten_record(record))
            self._csv_file.flush()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if self._csv_file is not None:
                self._csv_file.close()
        finally:
            if self._jsonl_file is not None:
                self._jsonl_file.close()


def write_outputs(
    records: list[dict[str, Any]], output_dir: Path, *, run_id: str
) -> dict[str, Path]:
    """輸出 canonical 最完整 JSONL 與方便 pandas/Excel 使用的 CSV。"""
    with StreamingRunWriter(output_dir, run_id=run_id, write_csv=True) as writer:
        for record in records:
            writer.append(record)
    return writer.paths


def append_jsonl(path: Path, item: dict[str, Any]) -> None:
    """逐筆追加 manifest/errors，讓中途停止時仍保留已完成的紀錄。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(json.dumps(item, ensure_ascii=False) + "\n")


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """逐筆讀取 JSONL；空白列會略過。"""

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path} 第 {line_number} 列不是合法 JSON") from error
            if not isinstance(value, dict):
                raise ValueError(f"{path} 第 {line_number} 列不是 JSON 物件")
            yield value


def rebuild_csv_from_jsonl(jsonl_path: Path, csv_path: Path) -> Path:
    """以 authoritative JSONL 原子重建衍生 CSV，供安全續跑使用。"""

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            prefix=f".{csv_path.stem}.",
            suffix=".tmp",
            dir=csv_path.parent,
            delete=False,
        ) as temporary:
            writer = csv.DictWriter(
                temporary,
                fieldnames=CSV_COLUMNS,
                extrasaction="ignore",
            )
            writer.writeheader()
            for record in iter_jsonl(jsonl_path):
                writer.writerow(flatten_record(record))
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, csv_path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return csv_path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """相容介面：需要整批資料時才將串流 iterator 轉成 list。"""

    return list(iter_jsonl(path))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )


def next_available_path(path: Path) -> Path:
    """回傳不會覆寫既有 snapshot 的路徑。

    正常首次擷取沿用原檔名；同一 run 續跑或中斷恢復時，若檔案已存在，
    依序加入 ``_002``、``_003``。這使 manifest 中的舊 SHA-256 永遠仍可
    對應到原本的 Raw 檔案。
    """

    if not path.exists():
        return path

    revision = 2
    while True:
        candidate = path.with_name(
            f"{path.stem}_{revision:03d}{path.suffix}"
        )
        if not candidate.exists():
            return candidate
        revision += 1


def write_json_snapshot(path: Path, value: Any) -> str:
    """以 UTF-8 儲存 API JSON snapshot，並回傳實際檔案內容的 SHA-256。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # 排序物件鍵，讓相同內容跨 Python process 仍得到相同 SHA-256。
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
