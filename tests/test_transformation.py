from pipeline import transformation as t
from tests.conftest import frame


def test_customers_are_standardised(batch_id):
    raw = frame([{"customer_id": " c0001 ", "first_name": "  aMARA ", "last_name": "o'brien",
                  "email": " Amara@Example.COM ", "country": "za", "signup_date": "2024-01-15"}])
    out = t.transform_customers(raw, batch_id).iloc[0]
    assert out["customer_id"] == "C0001"
    assert out["full_name"] == "Amara O'Brien"
    assert out["email"] == "amara@example.com"
    assert out["country"] == "ZA"


def test_orders_derive_amount_and_month(batch_id):
    raw = frame([{"order_id": "o1", "customer_id": "c1", "product_id": "p1", "quantity": "3",
                  "unit_price": "19.99", "order_date": "2025-03-07", "status": " SHIPPED"}])
    out = t.transform_orders(raw, batch_id).iloc[0]
    assert out["order_amount"] == 59.97
    assert out["order_month"] == "2025-03"
    assert out["status"] == "shipped"
    assert out["quantity"] == 3


def test_payments_timestamp_normalised(batch_id):
    raw = frame([{"payment_id": "pay1", "order_id": "o1", "amount": "10", "currency": "usd",
                  "payment_method": "CARD", "status": "Success", "paid_at": "2025-01-01T23:30:00Z"}])
    out = t.transform_payments(raw, batch_id).iloc[0]
    assert out["paid_at"] == "2025-01-01 23:30:00"
    assert out["paid_date"] == "2025-01-01"
    assert (out["currency"], out["payment_method"], out["status"]) == ("USD", "card", "success")
