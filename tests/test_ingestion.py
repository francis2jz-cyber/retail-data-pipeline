import json

import pytest
import requests

from mock_api.payment_api import start_in_background
from pipeline.ingestion import IngestionError, fetch_payments, read_csv_source


@pytest.fixture
def api(tmp_path):
    records = [{"payment_id": f"PAY{i}", "order_id": f"O{i}", "amount": 10.5, "currency": "USD",
                "payment_method": "card", "status": "success", "paid_at": "2025-01-01T00:00:00Z"}
               for i in range(23)]
    records[0]["amount"] = None
    path = tmp_path / "payments.json"
    path.write_text(json.dumps(records))
    server = start_in_background(path, port=0)
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_fetch_reads_every_page(api):
    df = fetch_payments(api, page_size=5)
    assert len(df) == 23
    assert df["payment_id"].is_unique


def test_fetched_values_are_raw_text(api):
    df = fetch_payments(api, page_size=50)
    assert df.loc[0, "amount"] == ""          # JSON null becomes empty text
    assert df.loc[1, "amount"] == "10.5"


class FlakySession:
    """Fails with 503 a set number of times, then succeeds."""
    def __init__(self, failures):
        self.failures, self.calls = failures, 0

    def get(self, url, params, timeout):
        self.calls += 1
        response = requests.Response()
        if self.calls <= self.failures:
            response.status_code = 503
        else:
            response.status_code = 200
            response._content = json.dumps({"data": [], "page": 1, "total_pages": 1}).encode()
        return response


def test_retries_transient_errors():
    session = FlakySession(failures=2)
    fetch_payments("http://fake", session=session, backoff=0)
    assert session.calls == 3


def test_gives_up_after_max_retries():
    with pytest.raises(IngestionError, match="unavailable after 3 attempts"):
        fetch_payments("http://fake", session=FlakySession(failures=10), backoff=0)


def test_missing_csv_column_is_reported(tmp_path):
    path = tmp_path / "orders.csv"
    path.write_text("order_id,customer_id\nO1,C1\n")
    with pytest.raises(IngestionError, match="missing columns"):
        read_csv_source(path, "orders")
