"""Runs everything in order: ingest, stage, validate, transform, reconcile, load + report."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

import pandas as pd
import requests

from pipeline import db, ingestion, loader, reconciliation, reporting, staging, transformation, validation
from pipeline.config import Settings

log = logging.getLogger("pipeline")


@dataclass
class PipelineResult:
    batch_id: str
    control_counts: pd.DataFrame
    control_totals: dict
    validation_errors: int
    reconciliation_exceptions: pd.DataFrame
    report_paths: dict


def new_batch_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:6]


def ensure_payment_api(settings: Settings):
    """Start the bundled mock API if nothing is answering at PAYMENT_API_URL."""
    try:
        requests.get(f"{settings.payment_api_url}/health", timeout=1).raise_for_status()
        log.info("Payment API reachable at %s", settings.payment_api_url)
        return None
    except requests.RequestException:
        if not settings.auto_start_mock_api:
            raise
    from mock_api.payment_api import start_in_background

    url = urlparse(settings.payment_api_url)
    server = start_in_background(settings.api_data_file, url.hostname or "127.0.0.1", url.port or 8765)
    log.info("Started mock Payment API at %s", settings.payment_api_url)
    return server


def run(settings: Settings | None = None, payment_session=None) -> PipelineResult:
    """payment_session lets tests inject a fake HTTP session for the payment source."""
    settings = settings or Settings()
    batch_id = new_batch_id()
    engine = db.get_engine(settings.database_url)
    db.init_schema(engine, settings.sql_dir)
    db.start_run(engine, batch_id, settings.backend)
    log.info("=== Batch %s started (%s) ===", batch_id, settings.backend)
    server = None
    try:
        if settings.payment_source == "mock" and payment_session is None:
            server = ensure_payment_api(settings)

        log.info("[1/6] Ingestion (payments from %s)", settings.payment_source)
        raw = ingestion.ingest_all(settings, payment_session)

        log.info("[2/6] Raw / staging")
        staging.stage_all(engine, raw, batch_id, settings.payment_source)

        log.info("[3/6] Validation")
        results = validation.validate_all(raw, batch_id, {settings.base_currency})
        errors = pd.concat([r.errors for r in results.values()], ignore_index=True)
        loader.append(engine, "err_validation_errors", errors)

        log.info("[4/6] Transformation")
        clean = transformation.transform_all({k: r.valid for k, r in results.items()}, batch_id)

        log.info("[5/6] Reconciliation")
        rejected_order_ids = set(results["orders"].invalid["order_id"].astype(str).str.strip().str.upper())
        recon = reconciliation.reconcile(clean["orders"], clean["payments"], clean["products"],
                                         rejected_order_ids, batch_id, settings.amount_tolerance,
                                         settings.settlement_window_days, settings.as_of_date or None)
        clean["orders"], clean["payments"] = recon.orders, recon.payments

        log.info("[6/6] Load + exception report")
        loaded = loader.load_core(engine, clean)
        loader.append(engine, "recon_exceptions", recon.exceptions)

        control_counts = pd.DataFrame([{
            "source": name,
            "ingested": len(raw[name]),
            "valid": len(results[name].valid),
            "rejected": len(results[name].invalid),
            "loaded": loaded[name],
        } for name in raw])
        report_paths = reporting.write_exception_report(
            settings.reports_dir, batch_id, settings.backend, control_counts,
            recon.control_totals, errors, recon.exceptions)

        db.finish_run(engine, batch_id, "success",
                      rows_ingested=int(control_counts["ingested"].sum()),
                      rows_valid=int(control_counts["valid"].sum()),
                      rows_rejected=int(control_counts["rejected"].sum()),
                      recon_exceptions=len(recon.exceptions))
        log.info("=== Batch %s finished ===", batch_id)
        return PipelineResult(batch_id, control_counts, recon.control_totals, len(errors),
                              recon.exceptions, report_paths)
    except Exception as exc:
        db.finish_run(engine, batch_id, "failed", error_message=str(exc)[:1000])
        log.exception("Batch %s failed", batch_id)
        raise
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()
        engine.dispose()
