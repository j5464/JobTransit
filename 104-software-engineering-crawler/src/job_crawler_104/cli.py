"""VS Code 終端機使用的爬蟲命令列入口。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .console import configure_utf8_console
from .crawler import CrawlOptions, crawl
from .paths import default_data_root, default_raw_root, project_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="擷取 104 台灣地區『軟體／工程類人員』全職職缺"
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=30,
        help="成功解析的目標筆數（預設 30；大型測試可設 10000）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="不顯示 Chrome 視窗；初次驗證建議先不用此參數",
    )
    parser.add_argument(
        "--min-delay", type=float, default=3.0, help="頁面間最短等待秒數（至少 3）"
    )
    parser.add_argument(
        "--max-delay", type=float, default=6.0, help="頁面間最長等待秒數"
    )
    parser.add_argument(
        "--timeout", type=int, default=25, help="主要內容顯式等待秒數"
    )
    parser.add_argument(
        "--max-search-pages", type=int, default=1000, help="搜尋結果最多翻頁數"
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=default_data_root(),
        help="latest 與 run exports 根目錄（預設 C:\\JobData\\job-crawler-104）",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="大型執行只串流寫 JSONL，不另外寫重複的 CSV",
    )
    parser.add_argument(
        "--sync-mysql",
        action="store_true",
        help="爬取結束後，將本次 JSONL 分批 upsert 到既有 MySQL jobs 表",
    )
    parser.add_argument(
        "--mysql-batch-size",
        type=int,
        default=500,
        help="MySQL 每次 transaction 的職缺筆數（預設 500）",
    )
    parser.add_argument(
        "--resume-run",
        dest="resume_run_id",
        default=None,
        help="續跑既有 run ID；會讀回 JSONL 並跳過已完成 job_id",
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=None,
        help=(
            "Raw JSON 儲存根目錄；省略時使用 "
            f"{default_raw_root()}"
        ),
    )
    return parser


def configure_logging(root: Path) -> None:
    log_path = root / "logs" / "crawler.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8"),
        ],
        force=True,
    )


def main(argv: list[str] | None = None) -> int:
    configure_utf8_console()
    args = build_parser().parse_args(argv)
    root = project_root()
    configure_logging(root)
    options = CrawlOptions(
        project_root=root,
        raw_root=args.raw_root,
        data_root=args.data_root,
        max_jobs=args.max_jobs,
        headless=args.headless,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        timeout=args.timeout,
        max_search_pages=args.max_search_pages,
        write_csv=not args.no_csv,
        sync_mysql=args.sync_mysql,
        mysql_batch_size=args.mysql_batch_size,
        resume_run_id=args.resume_run_id,
    )
    try:
        summary = crawl(options)
    except ValueError as error:
        print(f"參數錯誤：{error}", file=sys.stderr)
        return 2

    print("\n爬取完成摘要")
    print(f"- 狀態：{summary['status']}")
    print(f"- 筆數：{summary['record_count']}/{summary['target_count']}")
    for name, path in summary["outputs"].items():
        if path:
            print(f"- {name}: {path}")
    if summary["stop_reason"]:
        print(f"- 停止原因：{summary['stop_reason']}")
    return 0 if summary["status"] == "completed" else 2
