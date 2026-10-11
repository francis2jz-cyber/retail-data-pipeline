"""DB helpers. Kept to plain SQL so the same code works on SQLite and Postgres."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)


def get_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        Path(database_url.replace("sqlite:///", "", 1)).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url)


def _split_statements(sql: str) -> list[str]:
    statements = []
    for chunk in sql.split(";"):
        code_lines = [ln for ln in chunk.splitlines() if ln.strip() and not ln.strip().startswith("--")]
        if code_lines:
            statements.append(chunk.strip())
    return statements


def run_sql_file(engine: Engine, path: Path) -> None:
    with engine.begin() as conn:
        for statement in _split_statements(path.read_text(encoding="utf-8")):
            conn.exec_driver_sql(statement)


def init_schema(engine: Engine, sql_dir: Path) -> None:
    run_sql_file(engine, sql_dir / "schema.sql")
    log.info("Schema ready")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def start_run(engine: Engine, batch_id: str, backend: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_pipeline_runs (batch_id, started_at, status, database_backend) "
                "VALUES (:batch_id, :started_at, 'running', :backend)"
            ),
            {"batch_id": batch_id, "started_at": utc_now(), "backend": backend},
        )


def finish_run(engine: Engine, batch_id: str, status: str, **metrics) -> None:
    params = {
        "batch_id": batch_id,
        "finished_at": utc_now(),
        "status": status,
        "rows_ingested": metrics.get("rows_ingested"),
        "rows_valid": metrics.get("rows_valid"),
        "rows_rejected": metrics.get("rows_rejected"),
        "recon_exceptions": metrics.get("recon_exceptions"),
        "error_message": metrics.get("error_message"),
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE audit_pipeline_runs SET finished_at = :finished_at, status = :status, "
                "rows_ingested = :rows_ingested, rows_valid = :rows_valid, rows_rejected = :rows_rejected, "
                "recon_exceptions = :recon_exceptions, error_message = :error_message "
                "WHERE batch_id = :batch_id"
            ),
            params,
        )
