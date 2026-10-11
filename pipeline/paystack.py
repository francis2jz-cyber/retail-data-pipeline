"""Paystack as a payment source (test mode only).

Maps Paystack transactions onto the same raw layout the mock API produces, so nothing
downstream needs to know where the payments came from.
Docs: https://paystack.com/docs/api/transaction/#list

Notes on the mapping:
- amount is in cents, so divide by 100
- order id comes from metadata.order_id, or from the start of the reference
- statuses: success -> success, failed/abandoned -> failed, reversed -> refunded
- anything I don't recognise is passed through as-is so validation flags it

Only sk_test_ keys are accepted. This shouldn't ever be pointed at live data.

TODO: also pull /settlement so fees and bank payouts can be reconciled.
"""
from __future__ import annotations

import json
import logging
import re

import pandas as pd
import requests

from pipeline.ingestion import SOURCE_COLUMNS, IngestionError, _as_text, _get_with_retry

log = logging.getLogger(__name__)

STATUS_MAP = {
    "success": "success",
    "failed": "failed",
    "abandoned": "failed",
    "reversed": "refunded",
    "ongoing": "pending",
    "pending": "pending",
    "processing": "pending",
    "queued": "pending",
}
CHANNEL_MAP = {
    "card": "card",
    "eft": "eft",
    "bank": "eft",
    "bank_transfer": "eft",
    "capitec_pay": "eft",
    "apple_pay": "wallet",
    "mobile_money": "wallet",
    "qr": "wallet",
    "ussd": "wallet",
}
ORDER_REFERENCE = re.compile(r"^(O\d+)(?:[-_.=].*)?$")
MAX_PAGES = 10_000


def require_test_key(secret_key: str) -> None:
    if not secret_key:
        raise IngestionError("PAYSTACK_SECRET_KEY is not set. Add your test secret key (sk_test_...) to .env.")
    if not secret_key.startswith("sk_test_"):
        raise IngestionError("Refusing to use a non-test Paystack key. This project only accepts sk_test_ keys.")


def make_session(secret_key: str) -> requests.Session:
    require_test_key(secret_key)
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"})
    return session


def _metadata(txn: dict) -> dict:
    meta = txn.get("metadata")
    if isinstance(meta, str) and meta.strip():
        try:
            meta = json.loads(meta)
        except ValueError:
            return {}
    return meta if isinstance(meta, dict) else {}


def _order_id(txn: dict) -> str:
    order_id = _metadata(txn).get("order_id")
    if order_id:
        return str(order_id)
    match = ORDER_REFERENCE.match(str(txn.get("reference") or ""))
    return match.group(1) if match else ""


def _amount(value) -> str:
    """Paystack amounts are integers in the subunit. Anything else is passed through for validation to flag."""
    if value is None or value == "":
        return ""
    try:
        return f"{int(value) / 100:.2f}"
    except (TypeError, ValueError):
        return str(value)


def map_transaction(txn: dict) -> dict:
    status = str(txn.get("status") or "").lower()
    channel = str(txn.get("channel") or "").lower()
    reference = txn.get("reference") or (str(txn["id"]) if txn.get("id") is not None else "")
    return {
        "payment_id": str(reference),
        "order_id": _order_id(txn),
        "amount": _amount(txn.get("amount")),
        "currency": str(txn.get("currency") or ""),
        "payment_method": CHANNEL_MAP.get(channel, channel),
        "status": STATUS_MAP.get(status, status),
        "paid_at": str(txn.get("paid_at") or txn.get("paidAt") or txn.get("created_at") or txn.get("createdAt") or ""),
    }


def list_transactions(session, base_url: str, per_page: int = 100, max_retries: int = 4,
                      backoff: float = 1.0, timeout: float = 20.0) -> list[dict]:
    """Page through GET /transaction. Supports cursor pagination (meta.next) and offset pagination (meta.pageCount)."""
    url = f"{base_url.rstrip('/')}/transaction"
    params: dict = {"perPage": per_page, "use_cursor": "true"}
    records: list[dict] = []
    for pages in range(1, MAX_PAGES + 1):
        payload = _get_with_retry(session, url, params, max_retries, backoff, timeout)
        if payload.get("status") is False:
            raise IngestionError(f"Paystack returned an error: {payload.get('message')}")
        records.extend(payload.get("data") or [])
        meta = payload.get("meta") or {}
        if meta.get("next"):
            params = {"perPage": per_page, "use_cursor": "true", "next": meta["next"]}
        elif meta.get("pageCount") and int(meta.get("page", 1)) < int(meta["pageCount"]):
            params = {"perPage": per_page, "page": int(meta.get("page", 1)) + 1}
        else:
            log.info("Fetched %s Paystack transactions across %s page(s)", len(records), pages)
            return records
    raise IngestionError(f"Stopped after {MAX_PAGES} pages; pagination did not terminate")


def fetch_paystack_payments(secret_key: str, base_url: str = "https://api.paystack.co",
                            session=None, per_page: int = 100, **retry) -> pd.DataFrame:
    require_test_key(secret_key)
    session = session or make_session(secret_key)
    transactions = list_transactions(session, base_url, per_page, **retry)
    rows = [map_transaction(t) for t in transactions]
    return _as_text(pd.DataFrame(rows, columns=SOURCE_COLUMNS["payments"]), SOURCE_COLUMNS["payments"])
