"""從既有 JSONL 同步最新職缺到 MySQL，不重新執行爬蟲。"""

from job_crawler_104.mysql_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
