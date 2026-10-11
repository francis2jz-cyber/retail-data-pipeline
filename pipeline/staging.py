"""Lands each source in its stg_ table as-is, plus batch id / source / timestamp.

Only the latest batch is kept here - the history is in the error and recon tables.
"""
from __future__ import annotations

import logging

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pipeline.db import utc_now

log = logging.getLogger(__name__)

SOURCE_LABELS = {
    "customers": "customers.csv",
    "products": "inventory.csv",
    "orders": "orders.csv",
    "payments": "payment_api:/payments",
}


def stage_all(engine: Engine, raw: dict[str, pd.DataFrame], batch_id: str, payment_source: str = "mock") -> None:
    ingested_at = utc_now()
    labels = {**SOURCE_LABELS, "payments": "paystack:/transaction" if payment_source == "paystack"
              else SOURCE_LABELS["payments"]}
    with engine.begin() as conn:
        for name, df in raw.items():
            table = f"stg_{name}"
            staged = df.assign(_batch_id=batch_id, _source=labels[name], _ingested_at=ingested_at)
            conn.execute(text(f"DELETE FROM {table}"))
            staged.to_sql(table, conn, if_exists="append", index=False)
            log.info("Staged %s rows into %s", len(staged), table)
