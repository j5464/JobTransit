from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from job_crawler_104.crawler import CrawlOptions, build_search_url, create_run_id
from job_crawler_104.cli import build_parser
from job_crawler_104.paths import default_data_root, default_raw_root, raw_locator


class CrawlerConfigurationTests(unittest.TestCase):
    def test_search_url_has_all_approved_filters(self) -> None:
        query = parse_qs(urlparse(build_search_url(3)).query)

        self.assertEqual(query["area"], ["6001000000"])
        self.assertEqual(query["jobcat"], ["2007001000"])
        self.assertEqual(query["ro"], ["1"])
        self.assertEqual(query["page"], ["3"])
        self.assertEqual(query["searchJobs"], ["1"])

    def test_run_id_uses_windows_safe_taipei_timestamp(self) -> None:
        moment = datetime(
            2026,
            8,
            21,
            14,
            30,
            microsecond=123456,
            tzinfo=ZoneInfo("Asia/Taipei"),
        )
        self.assertEqual(create_run_id(moment), "20260821T143000123456+0800")

    def test_rejects_delay_below_three_seconds(self) -> None:
        options = CrawlOptions(project_root=PROJECT_ROOT, min_delay=2.9)
        with self.assertRaises(ValueError):
            options.validate()

    def test_allows_large_job_target_and_rejects_nonpositive_target(self) -> None:
        CrawlOptions(
            project_root=PROJECT_ROOT,
            max_jobs=10_000,
            max_search_pages=1_000,
        ).validate()
        with self.assertRaises(ValueError):
            CrawlOptions(project_root=PROJECT_ROOT, max_jobs=0).validate()

    def test_large_data_defaults_to_non_onedrive_root(self) -> None:
        self.assertEqual(
            default_data_root(), Path(r"C:\JobData\job-crawler-104")
        )

    def test_cli_exposes_large_run_storage_and_mysql_switches(self) -> None:
        args = build_parser().parse_args(
            ["--max-jobs", "10000", "--no-csv", "--sync-mysql"]
        )

        self.assertEqual(args.max_jobs, 10_000)
        self.assertEqual(args.data_root, Path(r"C:\JobData\job-crawler-104"))
        self.assertTrue(args.no_csv)
        self.assertTrue(args.sync_mysql)

    def test_raw_snapshot_defaults_to_local_app_data(self) -> None:
        raw_root = default_raw_root(local_app_data=r"C:\Users\demo\AppData\Local")

        self.assertEqual(
            raw_root,
            Path(r"C:\Users\demo\AppData\Local\job-crawler-104\raw"),
        )

    def test_raw_locator_is_root_relative_and_hides_windows_account(self) -> None:
        raw_root = Path(r"C:\Users\demo\AppData\Local\job-crawler-104\raw")
        snapshot = raw_root / "run123" / "detail" / "abc123.json"

        locator = raw_locator(snapshot, raw_root=raw_root)

        self.assertEqual(locator, "raw-root://run123/detail/abc123.json")
        self.assertNotIn("demo", locator)

    def test_raw_locator_rejects_file_outside_raw_root(self) -> None:
        with self.assertRaises(ValueError):
            raw_locator(Path(r"C:\outside\file.json"), raw_root=Path(r"C:\raw"))


if __name__ == "__main__":
    unittest.main()
