from __future__ import annotations

import copy
import csv
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from job_crawler_104.parser import parse_job_detail
from job_crawler_104.inspection import (
    choose_expected_count,
    derive_run_id,
    inspection_exit_code,
    latest_jsonl,
    main as inspect_main,
)
from job_crawler_104.quality import QualityAccumulator, build_quality_report
from job_crawler_104.storage import (
    StreamingRunWriter,
    flatten_record,
    next_available_path,
    write_json_snapshot,
    write_outputs,
)


FIXTURES = Path(__file__).parent / "fixtures"


def make_record() -> dict:
    html = (FIXTURES / "job_detail.html").read_text(encoding="utf-8")
    return parse_job_detail(
        html,
        job_url="https://www.104.com.tw/job/abc123",
        scraped_at="2026-08-21T14:30:00+08:00",
        run_id="20260821T143000+0800",
        search_page=1,
        raw_html_path="data/raw/20260821T143000+0800/detail/abc123.html",
    )


class StorageTests(unittest.TestCase):
    def test_streaming_writer_closes_jsonl_if_csv_open_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            writer = StreamingRunWriter(output_dir, run_id="broken-csv")
            writer.paths["csv"].mkdir(parents=True)

            with self.assertRaises(OSError):
                writer.__enter__()

            self.assertTrue(
                writer._jsonl_file is None or writer._jsonl_file.closed
            )

    def test_next_available_snapshot_path_never_overwrites_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "page_001.json"
            base.write_text("first", encoding="utf-8")
            second = next_available_path(base)
            second.write_text("second", encoding="utf-8")
            third = next_available_path(base)

        self.assertEqual(second.name, "page_001_002.json")
        self.assertEqual(third.name, "page_001_003.json")

    def test_flatten_record_keeps_raw_fields_and_valid_json_columns(self) -> None:
        row = flatten_record(make_record())

        self.assertEqual(row["source_job_id"], "abc123")
        self.assertEqual(row["job_title"], "Python 後端工程師")
        self.assertEqual(row["salary_raw"], "月薪 50,000~70,000 元")
        self.assertEqual(json.loads(row["tools_json"]), ["Python", "Git", "Docker"])
        self.assertIsInstance(json.loads(row["sections_json"]), list)

    def test_csv_neutralizes_formula_but_jsonl_preserves_source_text(self) -> None:
        record = make_record()
        record["company"]["name"] = '=HYPERLINK("https://example.com")'

        row = flatten_record(record)

        self.assertTrue(row["company_name"].startswith("'="))
        self.assertTrue(record["company"]["name"].startswith("="))

    def test_write_outputs_uses_utf8_jsonl_and_utf8_sig_csv(self) -> None:
        record = make_record()
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_outputs(
                [record], Path(temp_dir), run_id="20260821T143000+0800"
            )
            jsonl_text = paths["jsonl"].read_text(encoding="utf-8")
            csv_bytes = paths["csv"].read_bytes()

        self.assertIn("測試科技股份有限公司", jsonl_text)
        self.assertNotIn("\\u6e2c", jsonl_text)
        self.assertTrue(csv_bytes.startswith(b"\xef\xbb\xbf"))

    def test_snapshot_hash_is_stable_across_mapping_insertion_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first_hash = write_json_snapshot(
                root / "first.json", {"b": 2, "a": {"y": 2, "x": 1}}
            )
            second_hash = write_json_snapshot(
                root / "second.json", {"a": {"x": 1, "y": 2}, "b": 2}
            )

        self.assertEqual(first_hash, second_hash)

    def test_streaming_writer_persists_each_record_without_materializing_batch(self) -> None:
        first = make_record()
        second = copy.deepcopy(first)
        second["source"]["job_id"] = "def456"

        with tempfile.TemporaryDirectory() as temp_dir:
            with StreamingRunWriter(
                Path(temp_dir), run_id="stream-run", write_csv=True
            ) as writer:
                writer.append(first)
                writer.append(second)
                jsonl_path = writer.paths["jsonl"]
                csv_path = writer.paths["csv"]
                self.assertEqual(len(jsonl_path.read_text(encoding="utf-8").splitlines()), 2)
            csv_bytes = csv_path.read_bytes()

        self.assertTrue(csv_bytes.startswith(b"\xef\xbb\xbf"))

    def test_streaming_writer_resume_appends_without_duplicate_csv_header(self) -> None:
        first = make_record()
        second = copy.deepcopy(first)
        second["source"]["job_id"] = "def456"

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with StreamingRunWriter(
                output_dir, run_id="resume-run", write_csv=True
            ) as writer:
                writer.append(first)
            with StreamingRunWriter(
                output_dir,
                run_id="resume-run",
                write_csv=True,
                append_existing=True,
            ) as writer:
                writer.append(second)
            jsonl_lines = writer.paths["jsonl"].read_text(encoding="utf-8").splitlines()
            with writer.paths["csv"].open(
                "r", encoding="utf-8-sig", newline=""
            ) as csv_file:
                csv_rows = list(csv.DictReader(csv_file))

        self.assertEqual(len(jsonl_lines), 2)
        self.assertEqual(len(csv_rows), 2)
        self.assertEqual(
            [row["source_job_id"] for row in csv_rows], ["abc123", "def456"]
        )


class QualityReportTests(unittest.TestCase):
    def test_reports_counts_missingness_and_duplicate_ids(self) -> None:
        complete = make_record()
        partial = copy.deepcopy(complete)
        partial["source"]["job_id"] = "def456"
        partial["location"]["raw"] = None
        partial["salary"]["raw"] = None
        partial["quality"] = {
            "status": "partial",
            "warnings": ["missing_location", "missing_salary"],
        }
        duplicate = copy.deepcopy(complete)

        report = build_quality_report([complete, partial, duplicate], expected_count=30)

        self.assertEqual(report["record_count"], 3)
        self.assertEqual(report["unique_job_id_count"], 2)
        self.assertEqual(report["duplicate_job_id_count"], 1)
        self.assertEqual(report["target_shortfall"], 27)
        self.assertEqual(report["missing_fields"]["salary_raw"]["count"], 1)
        self.assertEqual(report["quality_status_counts"], {"ok": 2, "partial": 1})

    def test_streaming_accumulator_matches_legacy_batch_report(self) -> None:
        records = [make_record(), make_record()]
        records[1]["source"]["job_id"] = "def456"
        records[1]["salary"]["raw"] = None

        accumulator = QualityAccumulator()
        for record in records:
            accumulator.add(record)

        self.assertEqual(
            accumulator.build(expected_count=30),
            build_quality_report(records, expected_count=30),
        )


class InspectionTests(unittest.TestCase):
    def test_latest_jsonl_finds_streamed_run_under_large_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_root = root / "bulk-data"
            older = data_root / "runs" / "run001" / "jobs_run001.jsonl"
            latest = data_root / "runs" / "run002" / "jobs_run002.jsonl"
            older.parent.mkdir(parents=True)
            latest.parent.mkdir(parents=True)
            older.write_text("", encoding="utf-8")
            latest.write_text("", encoding="utf-8")

            selected = latest_jsonl(root, data_root=data_root)

        self.assertEqual(selected, latest)

    def test_derive_run_id_from_jobs_jsonl_filename(self) -> None:
        path = Path("data/extracted/jobs_20260821T143000+0800.jsonl")

        self.assertEqual(derive_run_id(path), "20260821T143000+0800")

    def test_explicit_expected_count_overrides_run_summary(self) -> None:
        summary = {"target_count": 30}

        self.assertEqual(choose_expected_count(2, summary), 2)

    def test_expected_count_uses_matching_run_summary_when_not_explicit(self) -> None:
        summary = {"target_count": 2}

        self.assertEqual(choose_expected_count(None, summary), 2)

    def test_expected_count_falls_back_to_30_without_run_summary(self) -> None:
        self.assertEqual(choose_expected_count(None, None), 30)

    def test_completed_nonempty_inspection_succeeds(self) -> None:
        self.assertEqual(
            inspection_exit_code(
                "completed", record_count=30, expected_count=30
            ),
            0,
        )

    def test_completed_but_short_inspection_returns_error(self) -> None:
        self.assertEqual(
            inspection_exit_code(
                "completed", record_count=1, expected_count=2
            ),
            2,
        )

    def test_blocked_or_failed_inspection_returns_error(self) -> None:
        for status in ("blocked", "failed"):
            with self.subTest(status=status):
                self.assertEqual(
                    inspection_exit_code(
                        status, record_count=1, expected_count=1
                    ),
                    2,
                )

    def test_empty_inspection_returns_error_even_when_run_completed(self) -> None:
        self.assertEqual(
            inspection_exit_code(
                "completed", record_count=0, expected_count=1
            ),
            2,
        )

    def test_main_uses_matching_summary_and_displays_run_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            jsonl_path = write_outputs(
                [make_record()], root / "data" / "extracted", run_id="run123"
            )["jsonl"]
            summary_path = root / "data" / "processed" / "run_summary_run123.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "run_id": "run123",
                        "status": "completed",
                        "stop_reason": None,
                        "target_count": 1,
                        "record_count": 1,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            output = StringIO()
            with patch(
                "job_crawler_104.inspection.project_root", return_value=root
            ), redirect_stdout(output):
                exit_code = inspect_main([str(jsonl_path)])

            inspection_report = json.loads(
                (root / "data" / "processed" / "inspection_jobs_run123.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(inspection_report["expected_count"], 1)
        self.assertIn("執行狀態：completed", output.getvalue())
        self.assertIn("停止原因：無", output.getvalue())


if __name__ == "__main__":
    unittest.main()
