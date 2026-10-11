"""Runs the queries in sql/analytics/ and gives back DataFrames."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine


def list_queries(sql_dir: Path) -> list[Path]:
    return sorted((sql_dir / "analytics").glob("*.sql"))


def describe(path: Path) -> str:
    """First comment line of the file is used as its title."""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("--"):
            return line.strip("- ").strip()
    return path.stem


def run_query(engine: Engine, path: Path) -> pd.DataFrame:
    sql = path.read_text(encoding="utf-8").strip().rstrip(";")
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn)
