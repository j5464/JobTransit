"""讀取最近一次 JSONL，列印並儲存資料品質報告。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .console import configure_utf8_console
from .paths import default_data_root, latest_run_jsonl, project_root
from .quality import QualityAccumulator, format_quality_summary, save_quality_report
from .storage import iter_jsonl


def latest_jsonl(root: Path, *, data_root: Path | None = None) -> Path | None:
    large_root = data_root or default_data_root()
    latest_run = latest_run_jsonl(large_root)
    if latest_run is not None:
        return latest_run
    legacy = list((root / "data" / "extracted").glob("jobs_*.jsonl"))
    return max(legacy, key=lambda path: path.stat().st_mtime) if legacy else None


def derive_run_id(path: Path) -> str | None:
    """從 ``jobs_<run_id>.jsonl`` 檔名取出可配對執行摘要的 run ID。"""
    if path.suffix.lower() != ".jsonl" or not path.stem.startswith("jobs_"):
        return None
    run_id = path.stem.removeprefix("jobs_")
    return run_id or None


def choose_expected_count(
    explicit_count: int | None, run_summary: dict[str, object] | None
) -> int:
    """決定品質報告的目標筆數；命令列明示值具有最高優先序。"""
    if explicit_count is not None:
        return explicit_count
    target_count = run_summary.get("target_count") if run_summary else None
    if isinstance(target_count, int) and not isinstance(target_count, bool):
        return target_count
    return 30


def inspection_exit_code(
    run_status: str | None,
    *,
    record_count: int,
    expected_count: int,
    summary_record_count: int | None = None,
) -> int:
    """只有狀態、目標筆數與摘要筆數互相一致時才回傳成功。"""
    summary_matches = (
        summary_record_count is None or summary_record_count == record_count
    )
    if (
        run_status == "completed"
        and record_count >= expected_count
        and summary_matches
    ):
        return 0
    return 2


def _load_matching_run_summary(
    root: Path, jsonl_path: Path
) -> dict[str, object] | None:
    """依 JSONL 檔名尋找同一次執行的摘要；沒有配對檔時回傳 ``None``。"""
    run_id = derive_run_id(jsonl_path)
    if run_id is None:
        return None
    summary_path = root / "data" / "processed" / f"run_summary_{run_id}.json"
    if not summary_path.exists():
        return None
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or summary.get("run_id") != run_id:
        return None
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="讀回 104 JSONL 並檢查資料品質")
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="要檢查的 JSONL；省略時使用 data root 的最新 run",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=default_data_root(),
        help="省略 path 時搜尋 JSONL 的大型資料根目錄",
    )
    parser.add_argument(
        "--expected-count",
        type=int,
        default=None,
        help="預期筆數；省略時優先採用 matching run summary 的 target_count",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_console()
    args = build_parser().parse_args(argv)
    root = project_root()
    path = args.path or latest_jsonl(root, data_root=args.data_root)
    if path is None:
        print("找不到 runs/*/jobs_*.jsonl，請先執行爬蟲。", file=sys.stderr)
        return 2
    if not path.is_absolute():
        path = (root / path).resolve()
    if not path.exists():
        print(f"找不到檔案：{path}", file=sys.stderr)
        return 2

    run_summary = _load_matching_run_summary(root, path)
    expected_count = choose_expected_count(args.expected_count, run_summary)
    accumulator = QualityAccumulator()
    for record in iter_jsonl(path):
        accumulator.add(record)
    report = accumulator.build(expected_count=expected_count)
    output_path = root / "data" / "processed" / f"inspection_{path.stem}.json"
    save_quality_report(report, output_path)

    status_value = run_summary.get("status") if run_summary else None
    run_status = status_value if isinstance(status_value, str) else None
    stop_value = run_summary.get("stop_reason") if run_summary else None
    stop_reason = stop_value if isinstance(stop_value, str) and stop_value else "無"
    summary_count_value = run_summary.get("record_count") if run_summary else None
    summary_record_count = (
        summary_count_value
        if isinstance(summary_count_value, int)
        and not isinstance(summary_count_value, bool)
        else None
    )

    print(format_quality_summary(report))
    print(f"- 執行狀態：{run_status or 'unknown'}")
    print(f"- 停止原因：{stop_reason}")
    print(f"- 完整報告：{output_path.relative_to(root)}")
    return inspection_exit_code(
        run_status,
        record_count=report["record_count"],
        expected_count=expected_count,
        summary_record_count=summary_record_count,
    )
