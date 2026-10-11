"""Reading the sources.

Everything is read as text on purpose. If a CSV has "abc" in the quantity column
I want that exact value to show up in the error table, not a NaN.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
import requests

log = logging.getLogger(__name__)

SOURCE_COLUMNS = {
    "customers": ["customer_id", "first_name", "last_name", "email", "country", "signup_date"],
    "products": ["product_id", "product_name", "category", "unit_price", "stock_quantity", "last_updated"],
    "orders": ["order_id", "customer_id", "product_id", "quantity", "unit_price", "order_date", "status"],
    "payments": ["payment_id", "order_id", "amount", "currency", "payment_method", "status", "paid_at"],
}
CSV_FILES = {"customers": "customers.csv", "products": "inventory.csv", "orders": "orders.csv"}


class IngestionError(RuntimeError):
    pass


def _as_text(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    df = df.reindex(columns=columns)
    return df.apply(lambda col: col.map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)))


def read_csv_source(path: Path, source: str) -> pd.DataFrame:
    if not path.exists():
        raise IngestionError(f"Source file not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = set(SOURCE_COLUMNS[source]) - set(df.columns)
    if missing:
        raise IngestionError(f"{path.name} is missing columns: {sorted(missing)}")
    log.info("Read %s rows from %s", len(df), path.name)
    return _as_text(df, SOURCE_COLUMNS[source])


def _get_with_retry(session, url: str, params: dict, max_retries: int, backoff: float, timeout: float) -> dict:
    for attempt in range(1, max_retries + 1):
        try:
            response = session.get(url, params=params, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:  # rate limited or server error
                raise requests.HTTPError(f"HTTP {response.status_code}")
            if response.status_code >= 400:  # client errors won't fix themselves, so don't retry
                raise IngestionError(f"API rejected request ({response.status_code}): {response.text}")
            return response.json()
        except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
            if attempt == max_retries:
                raise IngestionError(f"Payment API unavailable after {max_retries} attempts: {exc}") from exc
            wait = backoff * 2 ** (attempt - 1)
            log.warning("Payment API attempt %s failed (%s), retrying in %.1fs", attempt, exc, wait)
            time.sleep(wait)
    raise AssertionError("unreachable")


def fetch_payments(base_url: str, page_size: int = 250, session=None, max_retries: int = 3,
                   backoff: float = 0.5, timeout: float = 10.0) -> pd.DataFrame:
    """Pull every page from the Payment API and return the records as text."""
    session = session or requests.Session()
    records: list[dict] = []
    page = 1
    while True:
        payload = _get_with_retry(session, f"{base_url.rstrip('/')}/payments",
                                  {"page": page, "page_size": page_size}, max_retries, backoff, timeout)
        records.extend(payload["data"])
        if page >= payload["total_pages"]:
            break
        page += 1
    log.info("Fetched %s payments from API across %s page(s)", len(records), page)
    return _as_text(pd.DataFrame(records), SOURCE_COLUMNS["payments"])


def ingest_all(settings, payment_session=None) -> dict[str, pd.DataFrame]:
    data = {name: read_csv_source(settings.raw_data_dir / filename, name) for name, filename in CSV_FILES.items()}
    if settings.payment_source == "paystack":
        from pipeline.paystack import fetch_paystack_payments
        data["payments"] = fetch_paystack_payments(settings.paystack_secret_key, settings.paystack_base_url,
                                                   session=payment_session)
    elif settings.payment_source == "mock":
        data["payments"] = fetch_payments(settings.payment_api_url, settings.payment_api_page_size,
                                          session=payment_session)
    else:
        raise IngestionError(f"Unknown PAYMENT_SOURCE {settings.payment_source!r}; use 'mock' or 'paystack'")
    return data
