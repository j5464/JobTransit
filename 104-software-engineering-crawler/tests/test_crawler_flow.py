from __future__ import annotations

import copy
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import ANY, Mock, patch

from requests import Response
from requests.exceptions import Timeout


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from job_crawler_104.api_client import (
    MinimumDelayRetry,
    create_api_session,
    fetch_job_detail,
    fetch_search_page,
)
from job_crawler_104.crawler import (
    CrawlOptions,
    _candidate_from_api,
    _sanitized_detail,
    _sanitized_search,
    crawl,
)
from job_crawler_104.errors import (
    AccessBlocked,
    ApiPayloadError,
    Crawler104Error,
    JobPageParseError,
    JobUnavailable,
)


FIXTURE = Path(__file__).parent / "fixtures" / "job_detail_api.json"


class DummySession:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class ApiClientTests(unittest.TestCase):
    def test_candidate_rejects_job_id_with_path_characters(self) -> None:
        malicious = {
            "jobName": "不安全路徑",
            "link": {"job": r"https://www.104.com.tw/job/..\outside"},
        }

        self.assertIsNone(_candidate_from_api(malicious, page=1))
        self.assertIsNone(
            _candidate_from_api(
                {"link": {"job": "/job/" + "a" * 65}},
                page=1,
            )
        )
        safe = _candidate_from_api(
            {
                "jobName": "工程師 private@example.invalid 0912-345-678",
                "link": {"job": "https://www.104.com.tw/job/abc123"},
            },
            page=1,
        )
        self.assertNotIn("private@example.invalid", safe["title_hint"])
        self.assertNotIn("0912-345-678", safe["title_hint"])

    def test_search_api_403_or_429_is_reported_as_blocked(self) -> None:
        for status_code in (403, 429):
            with self.subTest(status_code=status_code):
                response = Response()
                response.status_code = status_code
                response.url = "https://www.104.com.tw/jobs/search/api/jobs"
                response._content = b"{}"
                session = Mock()
                session.get.return_value = response

                with self.assertRaises(AccessBlocked):
                    fetch_search_page(session, page=1)

                session.get.assert_called_once()

    def test_detail_404_or_410_is_skippable_unavailable_job(self) -> None:
        for status_code in (404, 410):
            with self.subTest(status_code=status_code):
                response = Response()
                response.status_code = status_code
                response.url = "https://www.104.com.tw/api/jobs/expired1"
                response._content = b"{}"
                session = Mock()
                session.get.return_value = response

                with self.assertRaises(JobUnavailable):
                    fetch_job_detail(session, job_id="expired1")

    def test_timeout_is_classified_as_transport_error(self) -> None:
        session = Mock()
        session.get.side_effect = Timeout("test timeout")

        with self.assertRaisesRegex(Crawler104Error, "逾時"):
            fetch_search_page(session, page=1)

    def test_invalid_json_is_classified_as_api_payload_error(self) -> None:
        response = Response()
        response.status_code = 200
        response.url = "https://www.104.com.tw/jobs/search/api/jobs"
        response._content = b"<html>challenge</html>"
        session = Mock()
        session.get.return_value = response

        with self.assertRaises(ApiPayloadError):
            fetch_search_page(session, page=1)

    def test_session_retries_only_temporary_server_errors(self) -> None:
        session = create_api_session(user_agent="test-current-browser")
        try:
            retry = session.get_adapter("https://").max_retries
            self.assertEqual(retry.total, 3)
            self.assertEqual(retry.backoff_factor, 1)
            self.assertEqual(set(retry.status_forcelist), {500, 502, 503, 504})
            self.assertNotIn(403, retry.status_forcelist)
            self.assertNotIn(429, retry.status_forcelist)
            self.assertFalse(retry.is_retry("GET", 429, has_retry_after=True))
        finally:
            session.close()

    def test_retry_waits_at_least_three_seconds_with_jitter(self) -> None:
        retry = MinimumDelayRetry(total=1, backoff_factor=1)

        with (
            patch(
                "job_crawler_104.api_client.random.uniform", return_value=0.5
            ),
            patch("job_crawler_104.api_client.time.sleep") as sleep_mock,
        ):
            retry.sleep()

        sleep_mock.assert_called_once_with(3.5)

    def test_sanitized_detail_removes_contact_and_personalized_state(self) -> None:
        data = {
            "contact": {"email": "private@example.invalid"},
            "interactionRecord": {"lastProcessedResumeAtTime": 123},
            "header": {
                "jobName": "工程師",
                "isSaved": True,
                "isApplied": True,
                "userApplyCount": 2,
                "unknownRecruiter": "不應保存",
            },
            "jobDetail": {
                "jobDescription": (
                    "開發系統，請寄 private@example.invalid、撥 +886 912 345 678"
                    "、02-2345-6789、037-123456、049-1234567、082-123456、"
                    "089-123456、0826-12345 或 0836-12345"
                ),
                "unexpectedPrivateObject": {"contactName": "王先生"},
            },
            "mystery": {"phone": "02-2345-6789", "contactName": "王先生"},
        }

        safe = _sanitized_detail(data)

        serialized = json.dumps(safe, ensure_ascii=False)
        self.assertNotIn("contact", safe)
        self.assertNotIn("interactionRecord", safe)
        self.assertNotIn("isSaved", safe["header"])
        self.assertNotIn("private@example.invalid", serialized)
        self.assertNotIn("+886 912 345 678", serialized)
        self.assertNotIn("02-2345-6789", serialized)
        for landline in (
            "037-123456",
            "049-1234567",
            "082-123456",
            "089-123456",
            "0826-12345",
            "0836-12345",
        ):
            self.assertNotIn(landline, serialized)
        self.assertNotIn("unknownRecruiter", serialized)
        self.assertNotIn("unexpectedPrivateObject", serialized)
        self.assertNotIn("mystery", serialized)
        self.assertIn("[已遮罩電子郵件]", serialized)
        self.assertIn("[已遮罩電話]", serialized)
        self.assertEqual(safe["header"]["jobName"], "工程師")

    def test_sanitized_search_removes_description_and_user_state(self) -> None:
        payload = {
            "data": [
                {
                    "jobName": "工程師",
                    "custName": "範例公司",
                    "description": "請寄到 private@example.invalid",
                    "isApplied": True,
                    "interactionRecord": {"nowTimestamp": 123},
                    "link": {
                        "job": "https://www.104.com.tw/job/abc123",
                        "cust": "https://www.104.com.tw/company/example",
                        "applyAnalyze": "https://example.invalid/private",
                    },
                }
            ],
            "metadata": {
                "pagination": {"currentPage": 1},
                "filterQuery": {"jobcat": ["2007001000"]},
                "personalBoost": 1,
            },
        }

        safe = _sanitized_search(payload)

        serialized = json.dumps(safe, ensure_ascii=False)
        self.assertIn("工程師", serialized)
        self.assertNotIn("private@example.invalid", serialized)
        self.assertNotIn("isApplied", serialized)
        self.assertNotIn("interactionRecord", serialized)
        self.assertNotIn("applyAnalyze", serialized)
        self.assertNotIn("personalBoost", serialized)
        self.assertIn("filterQuery", serialized)


class CrawlerFlowTests(unittest.TestCase):
    def test_keyboard_interrupt_closes_resources_and_writes_resumable_summary(self) -> None:
        candidate = {
            "job_id": "job0",
            "job_url": "https://www.104.com.tw/job/job0",
            "title_hint": "候選 0",
            "search_page": 1,
            "employment_code": 1,
        }
        session = DummySession()

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                data_root=root / "bulk-data",
                max_jobs=1,
                min_delay=3,
                max_delay=3,
                sync_mysql=True,
            )
            with (
                patch(
                    "job_crawler_104.crawler.create_run_id",
                    return_value="interrupt-run",
                ),
                patch(
                    "job_crawler_104.crawler.bootstrap_api_session",
                    return_value=session,
                ),
                patch(
                    "job_crawler_104.crawler.iter_api_candidates",
                    return_value=iter([candidate]),
                ),
                patch(
                    "job_crawler_104.crawler.polite_delay",
                    side_effect=KeyboardInterrupt,
                ),
                patch(
                    "job_crawler_104.crawler.sync_jsonl_to_mysql"
                ) as sync_mysql_mock,
                patch("job_crawler_104.crawler.LOGGER"),
            ):
                summary = crawl(options)

            summary_path = root / "data" / "processed" / "run_summary_interrupt-run.json"
            summary_exists = summary_path.is_file()

        self.assertEqual(summary["status"], "interrupted")
        self.assertIn("--resume-run", summary["stop_reason"])
        self.assertEqual(summary["mysql_sync"]["status"], "skipped_interrupted")
        sync_mysql_mock.assert_not_called()
        self.assertTrue(session.closed)
        self.assertTrue(summary_exists)

    def test_new_run_refuses_to_overwrite_existing_run_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_root = root / "bulk-data"
            (data_root / "runs" / "collision-run").mkdir(parents=True)
            options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                data_root=data_root,
                max_jobs=1,
                min_delay=3,
                max_delay=3,
            )

            with (
                patch(
                    "job_crawler_104.crawler.create_run_id",
                    return_value="collision-run",
                ),
                self.assertRaisesRegex(ValueError, "拒絕覆寫"),
            ):
                crawl(options)

    def test_resume_run_skips_completed_job_and_appends_until_target(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        candidates = [
            {
                "job_id": f"job{number}",
                "job_url": f"https://www.104.com.tw/job/job{number}",
                "title_hint": f"候選 {number}",
                "search_page": 1,
                "employment_code": 1,
            }
            for number in range(2)
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_root = root / "bulk-data"
            first_options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                data_root=data_root,
                max_jobs=1,
                min_delay=3,
                max_delay=3,
            )
            with (
                patch(
                    "job_crawler_104.crawler.bootstrap_api_session",
                    return_value=DummySession(),
                ),
                patch(
                    "job_crawler_104.crawler.iter_api_candidates",
                    return_value=iter(candidates),
                ),
                patch(
                    "job_crawler_104.crawler.fetch_job_detail",
                    return_value=fixture,
                ),
                patch(
                    "job_crawler_104.crawler.create_run_id",
                    return_value="resume-run",
                ),
                patch("job_crawler_104.crawler.polite_delay"),
                patch("job_crawler_104.crawler.LOGGER"),
            ):
                crawl(first_options)

            # 模擬 latest 檔案遺失；續跑應能由 durable run JSONL 自動重建。
            first_latest = data_root / "latest" / "jobs" / "jo" / "job0.json"
            first_latest.unlink()
            csv_path = data_root / "runs" / "resume-run" / "jobs_resume-run.csv"
            csv_header = csv_path.read_text(encoding="utf-8-sig").splitlines()[0]
            csv_path.write_text(csv_header + "\n", encoding="utf-8-sig")

            mismatched_csv_options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                data_root=data_root,
                max_jobs=2,
                min_delay=3,
                max_delay=3,
                write_csv=False,
                resume_run_id="resume-run",
            )
            with self.assertRaisesRegex(ValueError, "CSV"):
                crawl(mismatched_csv_options)

            resume_options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                data_root=data_root,
                max_jobs=2,
                min_delay=3,
                max_delay=3,
                resume_run_id="resume-run",
            )
            with (
                patch(
                    "job_crawler_104.crawler.bootstrap_api_session",
                    return_value=DummySession(),
                ),
                patch(
                    "job_crawler_104.crawler.iter_api_candidates",
                    return_value=iter(candidates),
                ),
                patch(
                    "job_crawler_104.crawler.fetch_job_detail",
                    return_value=fixture,
                ) as detail_mock,
                patch("job_crawler_104.crawler.polite_delay"),
                patch("job_crawler_104.crawler.LOGGER"),
            ):
                summary = crawl(resume_options)

            jsonl_path = (
                data_root / "runs" / "resume-run" / "jobs_resume-run.jsonl"
            )
            job_ids = [
                json.loads(line)["source"]["job_id"]
                for line in jsonl_path.read_text(encoding="utf-8").splitlines()
            ]
            with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
                csv_rows = list(csv.DictReader(csv_file))
            rebuilt_latest = first_latest.is_file()

        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["record_count"], 2)
        self.assertTrue(rebuilt_latest)
        self.assertEqual(job_ids, ["job0", "job1"])
        self.assertEqual([row["source_job_id"] for row in csv_rows], ["job0", "job1"])
        detail_mock.assert_called_once_with(ANY, job_id="job1")

    def test_streams_run_output_and_writes_one_latest_file_per_job(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        candidates = [
            {
                "job_id": f"job{number}",
                "job_url": f"https://www.104.com.tw/job/job{number}",
                "title_hint": f"候選 {number}",
                "search_page": 1,
                "employment_code": 1,
            }
            for number in range(2)
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_root = root / "bulk-data"
            options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                data_root=data_root,
                max_jobs=2,
                min_delay=3,
                max_delay=3,
            )
            with (
                patch(
                    "job_crawler_104.crawler.bootstrap_api_session",
                    return_value=DummySession(),
                ),
                patch(
                    "job_crawler_104.crawler.iter_api_candidates",
                    return_value=iter(candidates),
                ),
                patch(
                    "job_crawler_104.crawler.fetch_job_detail",
                    return_value=fixture,
                ),
                patch("job_crawler_104.crawler.polite_delay"),
                patch("job_crawler_104.crawler.LOGGER"),
                patch(
                    "job_crawler_104.crawler.create_run_id",
                    return_value="stream-run",
                ),
            ):
                summary = crawl(options)

            latest_files = sorted((data_root / "latest" / "jobs").rglob("*.json"))
            run_jsonl = data_root / "runs" / "stream-run" / "jobs_stream-run.jsonl"
            run_records = run_jsonl.read_text(encoding="utf-8").splitlines()

        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["record_count"], 2)
        self.assertEqual(summary["latest_written_count"], 2)
        self.assertEqual(len(latest_files), 2)
        self.assertEqual(len(run_records), 2)

    def test_continues_after_more_than_ten_bad_details_until_thirty_successes(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        candidates = [
            {
                "job_id": f"job{number:03d}",
                "job_url": f"https://www.104.com.tw/job/job{number:03d}",
                "title_hint": f"候選職缺 {number:03d}",
                "search_page": 1 if number < 32 else 2,
                "employment_code": 1,
            }
            for number in range(42)
        ]
        requested_ids: list[str] = []

        def fake_detail(_session: DummySession, *, job_id: str) -> dict:
            requested_ids.append(job_id)
            if len(requested_ids) <= 12:
                raise JobPageParseError("測試用無效詳情")
            data = copy.deepcopy(fixture)
            data["header"]["jobName"] = f"Python 工程師 {job_id}"
            return data

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = DummySession()
            options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                max_jobs=30,
                min_delay=3,
                max_delay=3,
            )
            with (
                patch(
                    "job_crawler_104.crawler.bootstrap_api_session",
                    return_value=session,
                ),
                patch(
                    "job_crawler_104.crawler.iter_api_candidates",
                    return_value=iter(candidates),
                ),
                patch(
                    "job_crawler_104.crawler.fetch_job_detail",
                    side_effect=fake_detail,
                ),
                patch("job_crawler_104.crawler.polite_delay"),
                patch("job_crawler_104.crawler.LOGGER"),
                patch(
                    "job_crawler_104.crawler.create_run_id",
                    return_value="test-run",
                ),
            ):
                summary = crawl(options)

            records_path = root / "data" / "extracted" / "jobs_test-run.jsonl"
            records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
            manifest = [
                json.loads(line)
                for line in (root / "raw" / "test-run" / "manifest.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]

        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["record_count"], 30)
        self.assertEqual(len(requested_ids), 42)
        self.assertEqual(len(records), 30)
        self.assertEqual(records[0]["source"]["job_id"], "job012")
        self.assertEqual(
            records[0]["source"]["requested_url"],
            "https://www.104.com.tw/api/jobs/job012",
        )
        self.assertTrue(
            records[0]["source"]["raw_payload_path"].startswith("raw-root://")
        )
        self.assertEqual(summary["outputs"]["raw_root"], "raw-root://")
        self.assertEqual(
            {item["transformation_version"] for item in manifest}, {"3.0"}
        )
        self.assertTrue(session.closed)

    def test_session_closes_when_search_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = DummySession()
            options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                max_jobs=1,
                min_delay=3,
                max_delay=3,
            )
            with (
                patch(
                    "job_crawler_104.crawler.bootstrap_api_session",
                    return_value=session,
                ),
                patch(
                    "job_crawler_104.crawler.iter_api_candidates",
                    side_effect=AccessBlocked("測試拒絕"),
                ),
                patch("job_crawler_104.crawler.LOGGER"),
                patch(
                    "job_crawler_104.crawler.create_run_id",
                    return_value="blocked-run",
                ),
            ):
                summary = crawl(options)

        self.assertEqual(summary["status"], "blocked")
        self.assertTrue(session.closed)

    def test_does_not_request_candidate_after_target_success(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        candidate_requests = 0

        def candidates():
            nonlocal candidate_requests
            for number in range(3):
                candidate_requests += 1
                yield {
                    "job_id": f"job{number}",
                    "job_url": f"https://www.104.com.tw/job/job{number}",
                    "title_hint": f"候選 {number}",
                    "search_page": 1,
                    "employment_code": 1,
                }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session = DummySession()
            options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                max_jobs=2,
                min_delay=3,
                max_delay=3,
            )
            with (
                patch(
                    "job_crawler_104.crawler.bootstrap_api_session",
                    return_value=session,
                ),
                patch(
                    "job_crawler_104.crawler.iter_api_candidates",
                    return_value=candidates(),
                ),
                patch(
                    "job_crawler_104.crawler.fetch_job_detail",
                    return_value=fixture,
                ),
                patch("job_crawler_104.crawler.polite_delay"),
                patch("job_crawler_104.crawler.LOGGER"),
                patch(
                    "job_crawler_104.crawler.create_run_id",
                    return_value="target-run",
                ),
            ):
                summary = crawl(options)

        self.assertEqual(summary["status"], "completed")
        self.assertEqual(candidate_requests, 2)

    def test_unavailable_jobs_do_not_trigger_three_failure_abort(self) -> None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        candidates = [
            {
                "job_id": f"job{number}",
                "job_url": f"https://www.104.com.tw/job/job{number}",
                "title_hint": f"候選 {number}",
                "search_page": 1,
                "employment_code": 1,
            }
            for number in range(5)
        ]
        calls = 0

        def fake_detail(_session: DummySession, *, job_id: str) -> dict:
            nonlocal calls
            calls += 1
            if calls <= 3:
                raise JobUnavailable(f"{job_id} 已關閉")
            return fixture

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                max_jobs=2,
                min_delay=3,
                max_delay=3,
            )
            with (
                patch(
                    "job_crawler_104.crawler.bootstrap_api_session",
                    return_value=DummySession(),
                ),
                patch(
                    "job_crawler_104.crawler.iter_api_candidates",
                    return_value=iter(candidates),
                ),
                patch(
                    "job_crawler_104.crawler.fetch_job_detail",
                    side_effect=fake_detail,
                ),
                patch("job_crawler_104.crawler.polite_delay"),
                patch("job_crawler_104.crawler.LOGGER"),
                patch(
                    "job_crawler_104.crawler.create_run_id",
                    return_value="unavailable-run",
                ),
            ):
                summary = crawl(options)

        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["record_count"], 2)
        self.assertEqual(calls, 5)

    def test_three_api_payload_errors_stop_as_failed(self) -> None:
        candidates = [
            {
                "job_id": f"job{number}",
                "job_url": f"https://www.104.com.tw/job/job{number}",
                "title_hint": f"候選 {number}",
                "search_page": 1,
                "employment_code": 1,
            }
            for number in range(4)
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            options = CrawlOptions(
                project_root=root,
                raw_root=root / "raw",
                max_jobs=1,
                min_delay=3,
                max_delay=3,
            )
            with (
                patch(
                    "job_crawler_104.crawler.bootstrap_api_session",
                    return_value=DummySession(),
                ),
                patch(
                    "job_crawler_104.crawler.iter_api_candidates",
                    return_value=iter(candidates),
                ),
                patch(
                    "job_crawler_104.crawler.fetch_job_detail",
                    side_effect=ApiPayloadError("格式改變"),
                ) as fetch_mock,
                patch("job_crawler_104.crawler.polite_delay"),
                patch("job_crawler_104.crawler.LOGGER"),
                patch(
                    "job_crawler_104.crawler.create_run_id",
                    return_value="payload-error-run",
                ),
            ):
                summary = crawl(options)

        self.assertEqual(summary["status"], "failed")
        self.assertEqual(fetch_mock.call_count, 3)
        self.assertIn("格式失敗", summary["stop_reason"])


if __name__ == "__main__":
    unittest.main()
