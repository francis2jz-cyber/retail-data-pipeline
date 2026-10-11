"""Run the SQL analytics queries and print the results.

    python scripts/run_analytics.py                 # run all
    python scripts/run_analytics.py --list          # show available queries
    python scripts/run_analytics.py monthly         # run queries whose file name contains "monthly"
    python scripts/run_analytics.py --csv           # also save each result to reports/analytics/
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.analytics import describe, list_queries, run_query  # noqa: E402
from pipeline.config import Settings  # noqa: E402
from pipeline.db import get_engine  # noqa: E402
from run_pipeline import DB_HELP  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SQL analytics")
    parser.add_argument("filter", nargs="?", default="", help="Only run queries whose file name contains this")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--csv", action="store_true", help="Save results to reports/analytics/")
    parser.add_argument("--database-url")
    args = parser.parse_args(argv)

    settings = Settings()
    if args.database_url:
        settings.database_url = args.database_url
    queries = [q for q in list_queries(settings.sql_dir) if args.filter in q.stem]

    if args.list:
        for q in queries:
            print(f"{q.stem:<32} {describe(q)}")
        return 0

    engine = get_engine(settings.database_url)
    out_dir = settings.reports_dir / "analytics"
    for q in queries:
        try:
            df = run_query(engine, q)
        except OperationalError as exc:
            print(DB_HELP.format(error=str(exc.orig).strip()), file=sys.stderr)
            return 1
        print(f"\n## {describe(q)}  ({q.name})\n")
        print(df.to_markdown(index=False, floatfmt=",.2f") if not df.empty else "(no rows)")
        if args.csv:
            out_dir.mkdir(parents=True, exist_ok=True)
            df.to_csv(out_dir / f"{q.stem}.csv", index=False)
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
