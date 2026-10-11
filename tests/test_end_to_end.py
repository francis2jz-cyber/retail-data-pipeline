"""Runs the real pipeline against a temporary SQLite database and checks that
it catches exactly the defects the generator planted (see defect_manifest.json)."""
import json

import pandas as pd
import pytest
from sqlalchemy import text

from mock_api.payment_api import start_in_background
from pipeline.analytics import list_queries, run_query
from pipeline.config import Settings
from pipeline.db import get_engine
from pipeline.orchestrator import run
from scripts.generate_sample_data import generate


@pytest.fixture(scope="module")
def pipeline_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    manifest = generate(tmp / "raw", tmp / "api", seed=123)
    server = start_in_background(tmp / "api" / "payments.json", port=0)
    settings = Settings(
        database_url=f"sqlite:///{(tmp / 'test.db').as_posix()}",
        raw_data_dir=tmp / "raw",
        api_data_file=tmp / "api" / "payments.json",
        reports_dir=tmp / "reports",
        payment_api_url=f"http://127.0.0.1:{server.server_address[1]}",
        auto_start_mock_api=False,
    )
    first = run(settings)
    second = run(settings)  # second run proves the load is idempotent
    yield manifest, settings, first, second
    server.shutdown()
    server.server_close()


def test_rejected_counts_match_planted_defects(pipeline_run):
    manifest, _, result, _ = pipeline_run
    rejected = dict(zip(result.control_counts["source"], result.control_counts["rejected"]))
    assert rejected == manifest["expected_rejected_records"]


def test_reconciliation_exceptions_match_planted_defects(pipeline_run):
    manifest, _, result, _ = pipeline_run
    found = result.reconciliation_exceptions["exception_type"].value_counts().to_dict()
    assert found == manifest["expected_reconciliation_exceptions"]


def test_recent_unpaid_orders_await_settlement(pipeline_run):
    manifest, settings, _, _ = pipeline_run
    with get_engine(settings.database_url).connect() as conn:
        awaiting = conn.execute(text(
            "SELECT COUNT(*) FROM fact_orders WHERE reconciliation_status = 'AWAITING_SETTLEMENT'")).scalar()
    assert awaiting == manifest["expected_awaiting_settlement_orders"]


def test_every_ingested_row_is_accounted_for(pipeline_run):
    _, _, result, _ = pipeline_run
    counts = result.control_counts
    assert (counts["ingested"] == counts["valid"] + counts["rejected"]).all()
    assert (counts["valid"] == counts["loaded"]).all()


def test_rerun_is_idempotent(pipeline_run):
    _, settings, first, second = pipeline_run
    engine = get_engine(settings.database_url)
    with engine.connect() as conn:
        loaded_orders = conn.execute(text("SELECT COUNT(*) FROM fact_orders")).scalar()
        runs = conn.execute(text("SELECT COUNT(*) FROM audit_pipeline_runs WHERE status = 'success'")).scalar()
    assert loaded_orders == first.control_counts.set_index("source").loc["orders", "loaded"]
    assert runs == 2
    pd.testing.assert_frame_equal(first.control_counts, second.control_counts)


def test_reports_are_written(pipeline_run):
    _, settings, result, _ = pipeline_run
    for path in result.report_paths.values():
        assert path.exists() and path.stat().st_size > 0
    assert (settings.reports_dir / "latest_exception_report.md").exists()


@pytest.mark.parametrize("query", list_queries(Settings().sql_dir), ids=lambda p: p.stem)
def test_analytics_query_runs(pipeline_run, query):
    _, settings, _, _ = pipeline_run
    df = run_query(get_engine(settings.database_url), query)
    assert not df.empty


# ---------------------------------------------------------------- Paystack mode
def as_paystack_transactions(payments: list[dict]) -> list[dict]:
    """Convert the generator's payments into transactions shaped like Paystack's API returns them."""
    out = []
    for n, p in enumerate(payments):
        amount = p["amount"]
        out.append({
            "id": 5_000_000 + n,
            "reference": p["payment_id"],
            "amount": None if amount is None else round(amount * 100),
            "currency": "ZAR" if p["currency"] == "USD" else p["currency"],
            "channel": p["payment_method"],
            "status": p["status"],
            "paid_at": p["paid_at"],
            "created_at": p["paid_at"],
            "metadata": json.dumps({"order_id": p["order_id"]}),
        })
    return out


def test_paystack_mode_finds_the_same_planted_defects(tmp_path):
    from tests.test_paystack import FakePaystack

    manifest = generate(tmp_path / "raw", tmp_path / "api", seed=77)
    payments = json.loads((tmp_path / "api" / "payments.json").read_text())
    settings = Settings(
        database_url=f"sqlite:///{(tmp_path / 'paystack.db').as_posix()}",
        raw_data_dir=tmp_path / "raw",
        reports_dir=tmp_path / "reports",
        payment_source="paystack",
        paystack_secret_key="sk_test_fake",
        base_currency="ZAR",
    )
    result = run(settings, payment_session=FakePaystack(as_paystack_transactions(payments), per_page=100))

    rejected = dict(zip(result.control_counts["source"], result.control_counts["rejected"]))
    assert rejected == manifest["expected_rejected_records"]
    found = result.reconciliation_exceptions["exception_type"].value_counts().to_dict()
    assert found == manifest["expected_reconciliation_exceptions"]
    with get_engine(settings.database_url).connect() as conn:
        source = conn.execute(text("SELECT DISTINCT _source FROM stg_payments")).scalar()
    assert source == "paystack:/transaction"
