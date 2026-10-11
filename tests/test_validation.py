import json

from pipeline import validation as v
from tests.conftest import frame


def customer(**overrides):
    row = {"customer_id": "C0001", "first_name": "Amara", "last_name": "Naidoo",
           "email": "amara@example.com", "country": "ZA", "signup_date": "2024-01-15"}
    row.update(overrides)
    return row


def test_clean_record_passes(batch_id):
    result = v.validate(frame([customer()]), "customers", "customer_id", v.CUSTOMER_RULES, batch_id)
    assert len(result.valid) == 1 and result.errors.empty


def test_blank_and_whitespace_values_count_as_missing(batch_id):
    df = frame([customer(email=""), customer(customer_id="C0002", email="   ")])
    result = v.validate(df, "customers", "customer_id", v.CUSTOMER_RULES, batch_id)
    assert len(result.valid) == 0
    assert set(result.errors["rule"]) == {"not_null"}


def test_malformed_email_rejected(batch_id):
    df = frame([customer(email="john@"), customer(customer_id="C0002", email="two@@x.com")])
    result = v.validate(df, "customers", "customer_id", v.CUSTOMER_RULES, batch_id)
    assert result.errors["rule"].tolist() == ["invalid_email", "invalid_email"]


def test_impossible_date_rejected(batch_id):
    result = v.validate(frame([customer(signup_date="2024-02-30")]), "customers", "customer_id",
                        v.CUSTOMER_RULES, batch_id)
    assert result.errors.iloc[0]["rule"] == "invalid_date"


def test_duplicate_keeps_first_occurrence(batch_id):
    df = frame([customer(), customer(first_name="Copy")])
    result = v.validate(df, "customers", "customer_id", v.CUSTOMER_RULES, batch_id)
    assert len(result.valid) == 1
    assert result.valid.iloc[0]["first_name"] == "Amara"
    assert result.errors.iloc[0]["rule"] == "duplicate_key"


def test_error_row_keeps_full_original_record(batch_id):
    result = v.validate(frame([customer(email="bad")]), "customers", "customer_id", v.CUSTOMER_RULES, batch_id)
    err = result.errors.iloc[0]
    assert err["record_key"] == "C0001" and err["invalid_value"] == "bad"
    assert json.loads(err["raw_record"])["first_name"] == "Amara"


def test_record_breaking_two_rules_logs_two_errors_but_one_rejection(batch_id):
    result = v.validate(frame([customer(email="bad", signup_date="nope")]), "customers", "customer_id",
                        v.CUSTOMER_RULES, batch_id)
    assert len(result.errors) == 2 and len(result.invalid) == 1


def test_orders_check_quantity_status_and_references(batch_id):
    base = {"order_id": "O1", "customer_id": "C1", "product_id": "P1", "quantity": "2",
            "unit_price": "10.00", "order_date": "2025-01-01", "status": " Completed "}
    rows = [base,
            {**base, "order_id": "O2", "quantity": "-1"},
            {**base, "order_id": "O3", "quantity": "1.5"},
            {**base, "order_id": "O4", "status": "lost"},
            {**base, "order_id": "O5", "customer_id": "C999"}]
    rules = v.order_rules({"C1"}, {"P1"})
    result = v.validate(frame(rows), "orders", "order_id", rules, batch_id)
    assert result.valid["order_id"].tolist() == ["O1"]  # messy status casing is fine
    assert dict(zip(result.errors["record_key"], result.errors["rule"])) == {
        "O2": "invalid_number", "O3": "invalid_number", "O4": "invalid_value", "O5": "unknown_reference"}


def test_payment_rules(batch_id):
    base = {"payment_id": "PAY1", "order_id": "O1", "amount": "10.5", "currency": "usd",
            "payment_method": "card", "status": "success", "paid_at": "2025-01-01T10:00:00Z"}
    rows = [base,
            {**base, "payment_id": "PAY2", "amount": "-5"},
            {**base, "payment_id": "PAY3", "currency": "XYZ"},
            {**base, "payment_id": "PAY4", "paid_at": "yesterday"}]
    result = v.validate(frame(rows), "payments", "payment_id", v.payment_rules({"USD"}), batch_id)
    assert result.valid["payment_id"].tolist() == ["PAY1"]
    assert len(result.invalid) == 3
