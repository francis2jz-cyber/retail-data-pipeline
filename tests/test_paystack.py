"""Tests for the Paystack connector, using a fake session that returns responses
shaped like the examples in Paystack's API documentation."""
import json

import pytest
import requests

from pipeline.ingestion import IngestionError
from pipeline.paystack import fetch_paystack_payments, map_transaction, require_test_key

KEY = "sk_test_fake"


def response(status_code, payload=None):
    r = requests.Response()
    r.status_code = status_code
    r._content = json.dumps(payload or {}).encode()
    return r


class FakePaystack:
    """Serves GET /transaction with cursor pagination (meta.next), like the real API."""

    def __init__(self, transactions, per_page=50, offset_style=False, fail_first=0):
        self.transactions, self.per_page = transactions, per_page
        self.offset_style, self.fail_first, self.calls = offset_style, fail_first, []

    def get(self, url, params, timeout):
        self.calls.append(dict(params))
        if len(self.calls) <= self.fail_first:
            return response(429, {"status": False, "message": "Rate limited"})
        assert url.endswith("/transaction")
        if self.offset_style:
            page = int(params.get("page", 1))
            start = (page - 1) * self.per_page
            count = max(1, -(-len(self.transactions) // self.per_page))
            meta = {"total": len(self.transactions), "perPage": self.per_page, "page": page, "pageCount": count}
        else:
            start = int(params.get("next", 0))
            nxt = start + self.per_page
            meta = {"next": str(nxt) if nxt < len(self.transactions) else None, "previous": None,
                    "perPage": self.per_page}
        data = self.transactions[start:start + self.per_page]
        return response(200, {"status": True, "message": "Transactions retrieved", "data": data, "meta": meta})


def txn(i, **overrides):
    base = {"id": 4099260000 + i, "domain": "test", "status": "success", "reference": f"ref{i}",
            "amount": 40333, "paid_at": "2025-08-22T09:15:02.000Z", "created_at": "2025-08-22T09:14:24.000Z",
            "channel": "card", "currency": "ZAR", "metadata": {"order_id": f"O{i:05d}"}}
    base.update(overrides)
    return base


# ------------------------------------------------------------------ mapping
def test_maps_documented_transaction_shape():
    row = map_transaction(txn(7))
    assert row == {"payment_id": "ref7", "order_id": "O00007", "amount": "403.33", "currency": "ZAR",
                   "payment_method": "card", "status": "success", "paid_at": "2025-08-22T09:15:02.000Z"}


def test_metadata_may_be_a_json_string():
    assert map_transaction(txn(1, metadata='{"order_id": "O00042"}'))["order_id"] == "O00042"


def test_order_id_falls_back_to_reference_prefix():
    assert map_transaction(txn(1, metadata="", reference="O00042-retry2"))["order_id"] == "O00042"
    assert map_transaction(txn(1, metadata=None, reference="re4lyvq3s3"))["order_id"] == ""


@pytest.mark.parametrize("paystack_status, ours", [("success", "success"), ("failed", "failed"),
                                                   ("abandoned", "failed"), ("reversed", "refunded"),
                                                   ("ongoing", "pending"), ("weird", "weird")])
def test_status_mapping(paystack_status, ours):
    assert map_transaction(txn(1, status=paystack_status))["status"] == ours


def test_channels_are_grouped():
    assert map_transaction(txn(1, channel="capitec_pay"))["payment_method"] == "eft"
    assert map_transaction(txn(1, channel="apple_pay"))["payment_method"] == "wallet"


def test_failed_transaction_without_paid_at_uses_created_at():
    row = map_transaction(txn(1, status="failed", paid_at=None))
    assert row["paid_at"] == "2025-08-22T09:14:24.000Z"


def test_missing_amount_is_left_blank_for_validation_to_catch():
    assert map_transaction(txn(1, amount=None))["amount"] == ""


# ------------------------------------------------------------------ fetching
def test_follows_cursor_pagination():
    fake = FakePaystack([txn(i) for i in range(120)], per_page=50)
    df = fetch_paystack_payments(KEY, session=fake)
    assert len(df) == 120 and df["payment_id"].is_unique
    assert len(fake.calls) == 3 and fake.calls[0]["use_cursor"] == "true"


def test_follows_offset_pagination():
    fake = FakePaystack([txn(i) for i in range(120)], per_page=50, offset_style=True)
    assert len(fetch_paystack_payments(KEY, session=fake)) == 120


def test_retries_when_rate_limited():
    fake = FakePaystack([txn(1)], fail_first=2)
    df = fetch_paystack_payments(KEY, session=fake, backoff=0)
    assert len(df) == 1 and len(fake.calls) == 3


@pytest.mark.parametrize("key", ["", "sk_live_abc123", "pk_test_abc"])
def test_refuses_missing_or_non_test_keys(key):
    with pytest.raises(IngestionError):
        require_test_key(key)
