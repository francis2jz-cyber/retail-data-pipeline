import pandas as pd
import pytest

from pipeline.reconciliation import reconcile


def order(order_id, amount, status="completed"):
    return {"order_id": order_id, "customer_id": "C1", "product_id": f"P-{order_id}", "quantity": 1,
            "unit_price": amount, "order_amount": amount, "status": status, "order_date": "2025-06-01"}


def payment(payment_id, order_id, amount, status="success"):
    return {"payment_id": payment_id, "order_id": order_id, "amount": amount, "status": status}


def catalog_for(orders: pd.DataFrame, overrides: dict | None = None) -> pd.DataFrame:
    """Catalog where every product's list price equals what the order paid, unless overridden."""
    products = orders[["product_id", "unit_price"]].rename(columns={"unit_price": "list_price"})
    for product_id, price in (overrides or {}).items():
        products.loc[products["product_id"] == product_id, "list_price"] = price
    return products


@pytest.fixture
def scenario(batch_id):
    orders = pd.DataFrame([
        order("O1", 100.0),                     # matched
        order("O2", 50.0),                      # missing payment
        order("O3", 80.0),                      # amount mismatch
        order("O4", 30.0),                      # duplicate payment
        order("O5", 40.0, status="cancelled"),  # charged although cancelled
        order("O6", 90.0),                      # sold below catalog price (100)
        order("O7", 20.0, status="pending"),    # pending, no payment yet
        order("O8", 60.0),                      # failed attempt then success -> matched
    ])
    payments = pd.DataFrame([
        payment("PAY1", "O1", 100.0),
        payment("PAY3", "O3", 85.0),
        payment("PAY4A", "O4", 30.0), payment("PAY4B", "O4", 30.0),
        payment("PAY5", "O5", 40.0),
        payment("PAY6", "O6", 90.0),
        payment("PAY8A", "O8", 60.0, status="failed"), payment("PAY8B", "O8", 60.0),
        payment("PAY9", "O999", 12.0),          # orphan: order exists nowhere
        payment("PAY10", "OREJ", 15.0),         # order was rejected by validation
    ])
    products = catalog_for(orders, {"P-O6": 100.0})
    return reconcile(orders, payments, products, {"OREJ"}, batch_id, as_of="2025-07-01")  # a month later


def test_each_exception_type_is_detected_once(scenario):
    counts = scenario.exceptions["exception_type"].value_counts().to_dict()
    assert counts == {"MISSING_PAYMENT": 1, "AMOUNT_MISMATCH": 1, "DUPLICATE_PAYMENT": 1,
                      "PAYMENT_ON_CANCELLED_ORDER": 1, "PRICE_MISMATCH": 1,
                      "ORPHAN_PAYMENT": 1, "PAYMENT_FOR_REJECTED_ORDER": 1}


def test_order_statuses(scenario):
    status = dict(zip(scenario.orders["order_id"], scenario.orders["reconciliation_status"]))
    assert status == {"O1": "MATCHED", "O2": "MISSING_PAYMENT", "O3": "AMOUNT_MISMATCH",
                      "O4": "DUPLICATE_PAYMENT", "O5": "PAYMENT_ON_CANCELLED_ORDER", "O6": "MATCHED",
                      "O7": "AWAITING_PAYMENT", "O8": "MATCHED"}


def test_payment_statuses(scenario):
    status = dict(zip(scenario.payments["payment_id"], scenario.payments["reconciliation_status"]))
    assert status["PAY8A"] == "NOT_SETTLED"
    assert status["PAY9"] == "ORPHAN_PAYMENT"
    assert status["PAY10"] == "PAYMENT_FOR_REJECTED_ORDER"
    assert status["PAY4A"] == status["PAY4B"] == "DUPLICATE_PAYMENT"


def test_amount_mismatch_difference(scenario):
    row = scenario.exceptions.query("exception_type == 'AMOUNT_MISMATCH'").iloc[0]
    assert (row["expected_amount"], row["actual_amount"], row["difference"]) == (80.0, 85.0, 5.0)


def test_tolerance_absorbs_rounding(batch_id):
    orders = pd.DataFrame([order("O1", 10.00)])
    payments = pd.DataFrame([payment("PAY1", "O1", 10.005)])
    result = reconcile(orders, payments, catalog_for(orders), set(), batch_id, tolerance=0.01)
    assert result.exceptions.empty


def test_control_totals(scenario):
    totals = scenario.control_totals
    assert totals["expected_revenue_billable_orders"] == 100 + 50 + 80 + 30 + 90 + 60
    assert totals["settled_payments_unmatched"] == 27.0


# ------------------------------------------------------------------ settlement window
def dated(order_id, amount, order_date, status="completed"):
    return {**order(order_id, amount, status), "order_date": order_date}


@pytest.fixture
def timing_orders():
    return pd.DataFrame([
        dated("OLD", 10.0, "2025-12-01"),     # 30 days old, unpaid -> missing
        dated("EDGE", 10.0, "2025-12-29"),    # exactly 2 days old -> still within window
        dated("NEW", 10.0, "2025-12-31"),     # same day as the cut-off
    ])


def no_payments():
    return pd.DataFrame(columns=["payment_id", "order_id", "amount", "status"])


def test_recent_unpaid_orders_await_settlement(batch_id, timing_orders):
    result = reconcile(timing_orders, no_payments(), catalog_for(timing_orders), set(), batch_id,
                       settlement_window_days=2)
    status = dict(zip(result.orders["order_id"], result.orders["reconciliation_status"]))
    assert status == {"OLD": "MISSING_PAYMENT", "EDGE": "AWAITING_SETTLEMENT", "NEW": "AWAITING_SETTLEMENT"}
    assert result.exceptions["order_id"].tolist() == ["OLD"]
    assert "30 days" in result.exceptions.iloc[0]["details"]


def test_zero_day_window_flags_everything_older_than_today(batch_id, timing_orders):
    result = reconcile(timing_orders, no_payments(), catalog_for(timing_orders), set(), batch_id,
                       settlement_window_days=0)
    assert sorted(result.exceptions["order_id"]) == ["EDGE", "OLD"]


def test_explicit_as_of_date(batch_id, timing_orders):
    result = reconcile(timing_orders, no_payments(), catalog_for(timing_orders), set(), batch_id,
                       settlement_window_days=2, as_of="2026-01-10")
    assert len(result.exceptions) == 3  # ten days later, all three are overdue


def test_control_totals_exclude_window(batch_id, timing_orders):
    totals = reconcile(timing_orders, no_payments(), catalog_for(timing_orders), set(), batch_id).control_totals
    assert totals["within_settlement_window"] == 20.0
    assert totals["expected_revenue_due"] == 10.0
    assert totals["net_difference"] == -10.0
