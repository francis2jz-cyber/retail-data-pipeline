"""Run the full pipeline.

    python run_pipeline.py                 # uses SQLite, no setup needed
    python run_pipeline.py --regenerate    # rebuild the sample data first
    python run_pipeline.py --database-url postgresql+psycopg2://user:pass@localhost:5432/retail
    python run_pipeline.py --payment-source paystack     # pull payments from your Paystack test account
    python run_pipeline.py --settlement-window 3 --as-of 2025-12-31
"""
from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy.exc import OperationalError

from pipeline.config import PROJECT_ROOT, Settings


DB_HELP = """
Could not connect to the database:
  {error}

If you are using PostgreSQL, check that:
  1. The PostgreSQL service is running (Windows: Services app; macOS: Postgres.app / brew services)
  2. The database exists:  CREATE DATABASE retail;
  3. DATABASE_URL in your .env has the right user, password, host and port
Or remove DATABASE_URL to use the built-in SQLite database instead.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retail data pipeline")
    parser.add_argument("--database-url", help="Override DATABASE_URL (default: local SQLite file)")
    parser.add_argument("--regenerate", action="store_true", help="Regenerate sample data before running")
    parser.add_argument("--payment-source", choices=["mock", "paystack"], help="Where payments come from")
    parser.add_argument("--settlement-window", type=int, metavar="DAYS",
                        help="Days a billable order may wait for payment before it is flagged")
    parser.add_argument("--as-of", metavar="YYYY-MM-DD", help="Date to measure order age against")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s", datefmt="%H:%M:%S")

    settings = Settings()
    if args.database_url:
        settings.database_url = args.database_url
    if args.payment_source:
        settings.payment_source = args.payment_source
    if args.settlement_window is not None:
        settings.settlement_window_days = args.settlement_window
    if args.as_of:
        settings.as_of_date = args.as_of

    if args.regenerate or not (settings.raw_data_dir / "orders.csv").exists():
        from scripts.generate_sample_data import generate
        generate(settings.raw_data_dir, settings.api_data_file.parent)
        logging.info("Sample data generated")

    from pipeline.ingestion import IngestionError
    from pipeline.orchestrator import run
    try:
        result = run(settings)
    except OperationalError as exc:
        print(DB_HELP.format(error=str(exc.orig).strip()), file=sys.stderr)
        return 1
    except IngestionError as exc:
        print(f"\nCould not read a source:\n  {exc}\n", file=sys.stderr)
        return 1

    print("\n" + "=" * 70)
    print(f"Batch {result.batch_id} complete\n")
    print(result.control_counts.to_string(index=False))
    print(f"\nValidation errors logged:      {result.validation_errors}")
    print(f"Reconciliation exceptions:     {len(result.reconciliation_exceptions)}")
    print(f"Payments from:                 {settings.payment_source}   "
          f"(settlement window: {settings.settlement_window_days} days)")
    for key, value in result.control_totals.items():
        print(f"  {key.replace('_', ' '):<32} {value:>14,.2f}")
    report = result.report_paths["markdown"]
    shown = report.relative_to(PROJECT_ROOT) if report.is_relative_to(PROJECT_ROOT) else report
    print(f"\nException report: {shown}")
    print("Next: python scripts/run_analytics.py")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
