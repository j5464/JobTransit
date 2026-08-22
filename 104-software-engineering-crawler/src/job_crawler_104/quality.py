"""讀回爬取結果並計算第一階段資料品質指標。"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .storage import write_json


def _nested(record: dict[str, Any], *keys: str) -> Any:
    value: Any = record
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _city_from_location(location: str | None) -> str:
    if not location:
        return "(缺失)"
    match = re.match(r"^(.{2,3}[縣市])", location)
    return match.group(1) if match else "(待解析)"


FIELD_GETTERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "job_title": lambda row: _nested(row, "job", "title"),
    "company_name": lambda row: _nested(row, "company", "name"),
    "location_raw": lambda row: _nested(row, "location", "raw"),
    "salary_raw": lambda row: _nested(row, "salary", "raw"),
    "job_description_text": lambda row: _nested(
        row, "job", "description", "text"
    ),
    "requirements_text": lambda row: _nested(row, "requirements", "text"),
}


class QualityAccumulator:
    """以固定大小的 Counter 逐筆累積品質資料，避免保存整批 records。"""

    def __init__(self) -> None:
        self.record_count = 0
        self.job_ids: set[str] = set()
        self.missing_counts = {name: 0 for name in FIELD_GETTERS}
        self.status_counts: Counter[str] = Counter()
        self.warning_counts: Counter[str] = Counter()
        self.salary_counts: Counter[str] = Counter()
        self.employment_counts: Counter[str] = Counter()
        self.city_counts: Counter[str] = Counter()
        self.sample: list[dict[str, Any]] = []

    def add(self, record: dict[str, Any]) -> None:
        self.record_count += 1
        for name, getter in FIELD_GETTERS.items():
            if getter(record) in (None, "", []):
                self.missing_counts[name] += 1

        self.job_ids.add(str(_nested(record, "source", "job_id")))
        self.status_counts[str(_nested(record, "quality", "status"))] += 1
        self.warning_counts.update(_nested(record, "quality", "warnings") or [])
        self.salary_counts[_nested(record, "salary", "raw") or "(缺失)"] += 1
        self.employment_counts[
            _nested(record, "job", "employment_type_raw") or "(缺失)"
        ] += 1
        self.city_counts[
            _city_from_location(_nested(record, "location", "raw"))
        ] += 1
        if len(self.sample) < 3:
            self.sample.append(
                {
                    "job_id": _nested(record, "source", "job_id"),
                    "job_title": _nested(record, "job", "title"),
                    "company_name": _nested(record, "company", "name"),
                    "location_raw": _nested(record, "location", "raw"),
                    "salary_raw": _nested(record, "salary", "raw"),
                }
            )

    def build(self, *, expected_count: int) -> dict[str, Any]:
        total = self.record_count
        missing_fields = {
            name: {
                "count": count,
                "rate": round(count / total, 4) if total else None,
            }
            for name, count in self.missing_counts.items()
        }
        unique_count = len(self.job_ids)
        return {
            "expected_count": expected_count,
            "record_count": total,
            "target_shortfall": max(0, expected_count - total),
            "unique_job_id_count": unique_count,
            "duplicate_job_id_count": total - unique_count,
            "quality_status_counts": dict(self.status_counts),
            "warning_counts": dict(self.warning_counts),
            "missing_fields": missing_fields,
            "employment_type_counts": dict(self.employment_counts),
            "city_counts": dict(self.city_counts.most_common()),
            "salary_raw_top20": dict(self.salary_counts.most_common(20)),
            "sample": list(self.sample),
        }


def build_quality_report(
    records: list[dict[str, Any]], *, expected_count: int
) -> dict[str, Any]:
    """產生列數、唯一性、缺失值與常見原始值統計。"""
    accumulator = QualityAccumulator()
    for record in records:
        accumulator.add(record)
    return accumulator.build(expected_count=expected_count)


def save_quality_report(report: dict[str, Any], path: Path) -> None:
    write_json(path, report)


def format_quality_summary(report: dict[str, Any]) -> str:
    """產生適合 VS Code 終端機閱讀的繁體中文摘要。"""
    lines = [
        "資料品質摘要",
        f"- 目標筆數：{report['expected_count']}",
        f"- 實際筆數：{report['record_count']}",
        f"- 唯一職缺 ID：{report['unique_job_id_count']}",
        f"- 重複職缺 ID：{report['duplicate_job_id_count']}",
        f"- 解析狀態：{report['quality_status_counts']}",
        "- 主要欄位缺失：",
    ]
    for field, result in report["missing_fields"].items():
        rate = result["rate"]
        rate_text = "N/A" if rate is None else f"{rate:.1%}"
        lines.append(f"  - {field}: {result['count']} 筆 ({rate_text})")
    lines.append(f"- 地區分布：{report['city_counts']}")
    lines.append(f"- 工作性質：{report['employment_type_counts']}")
    return "\n".join(lines)
