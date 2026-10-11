"""Loads the clean tables.

The sources are full snapshots, so I just delete and reinsert inside one transaction.
If it fails halfway nothing changes, and running it twice gives the same result.
The error/exception tables are append-only so each batch's history is kept.

TODO: incremental upserts instead of full refresh if the data gets big.
"""
from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# Insert parents before children; delete in the reverse order (foreign keys).
LOAD_ORDER = [("dim_customers", "customers"), ("dim_products", "products"),
              ("fact_orders", "orders"), ("fact_payments", "payments")]


def load_core(engine: Engine, tables: dict[str, pd.DataFrame]) -> dict[str, int]:
    loaded = {}
    with engine.begin() as conn:
        for table, _ in reversed(LOAD_ORDER):
            conn.execute(text(f"DELETE FROM {table}"))
        for table, key in LOAD_ORDER:
            tables[key].to_sql(table, conn, if_exists="append", index=False, chunksize=1000)
            loaded[key] = len(tables[key])
            log.info("Loaded %s rows into %s", len(tables[key]), table)
    return loaded


def append(engine: Engine, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    with engine.begin() as conn:
        df.to_sql(table, conn, if_exists="append", index=False, chunksize=1000)
    log.info("Appended %s rows to %s", len(df), table)
