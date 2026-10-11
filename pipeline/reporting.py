"""Writes the exception report (markdown so it renders on GitHub) plus CSV extracts."""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from pipeline.db import utc_now


def _md(df: pd.DataFrame) -> str:
    return df.to_markdown(index=False, floatfmt=",.2f") if not df.empty else "_None_"


def write_exception_report(reports_dir: Path, batch_id: str, backend: str, control_counts: pd.DataFrame,
                           control_totals: dict, errors: pd.DataFrame, exceptions: pd.DataFrame) -> dict[str, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "markdown": reports_dir / f"exception_report_{batch_id}.md",
        "exceptions_csv": reports_dir / f"reconciliation_exceptions_{batch_id}.csv",
        "errors_csv": reports_dir / f"validation_errors_{batch_id}.csv",
    }

    errors_by_rule = (errors.groupby(["source", "rule", "column_name"]).size()
                      .reset_index(name="errors").sort_values(["source", "errors"], ascending=[True, False])
                      if not errors.empty else pd.DataFrame())
    by_type = (exceptions.assign(abs_difference=exceptions["difference"].abs())
               .groupby(["exception_type", "severity"])
               .agg(count=("exception_type", "size"), total_abs_difference=("abs_difference", "sum"))
               .reset_index().sort_values("count", ascending=False)
               if not exceptions.empty else pd.DataFrame())
    high = exceptions[exceptions["severity"] == "high"][
        ["exception_type", "order_id", "payment_id", "expected_amount", "actual_amount", "difference", "details"]
    ].sort_values(["exception_type", "order_id"]).head(25).assign(payment_id=lambda d: d["payment_id"].fillna(""))
    totals = pd.DataFrame([{"metric": k.replace("_", " "), "value": v} for k, v in control_totals.items()])

    lines = [
        "# Pipeline Exception Report", "",
        f"- **Batch:** `{batch_id}`",
        f"- **Generated (UTC):** {utc_now()}",
        f"- **Database:** {backend}", "",
        "## 1. Record counts", "", _md(control_counts), "",
        "## 2. Financial control totals", "", _md(totals), "",
        "## 3. Data quality: validation errors by rule", "",
        "A record can break more than one rule, so error counts can exceed rejected record counts.", "",
        _md(errors_by_rule), "",
        "## 4. Reconciliation exceptions by type", "", _md(by_type), "",
        "## 5. High-severity exceptions (first 25)", "", _md(high), "",
        f"Full detail: `{paths['exceptions_csv'].name}` and `{paths['errors_csv'].name}`.", "",
    ]
    paths["markdown"].write_text("\n".join(lines), encoding="utf-8")
    exceptions.to_csv(paths["exceptions_csv"], index=False)
    errors.drop(columns=["raw_record"]).to_csv(paths["errors_csv"], index=False)
    shutil.copyfile(paths["markdown"], reports_dir / "latest_exception_report.md")
    return paths
