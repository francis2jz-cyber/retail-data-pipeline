"""Reconciliation: do orders, payments and the catalog agree with each other?

Validation only checks records one at a time. A payment can be perfectly valid
and still be wrong (charged twice, or for an order that doesn't exist).

Exceptions raised:
    MISSING_PAYMENT             completed/shipped order, no successful payment
                                (only once it's older than the settlement window)
    AMOUNT_MISMATCH             paid amount != order amount
    DUPLICATE_PAYMENT           more than one successful payment for an order
    PAYMENT_ON_CANCELLED_ORDER  cancelled order but the card was still charged
    PRICE_MISMATCH              sold at a different price than the catalog
    ORPHAN_PAYMENT              payment for an order id that doesn't exist anywhere
    PAYMENT_FOR_REJECTED_ORDER  payment for an order that failed validation

Settlement window: payments often land a day or two after the order, so an unpaid
order is tagged AWAITING_SETTLEMENT until it's older than the window. Age is measured
against as_of (defaults to the latest order date in the extract).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from pipeline.db import utc_now

EXCEPTION_COLUMNS = ["batch_id", "exception_type", "severity", "order_id", "payment_id",
                     "expected_amount", "actual_amount", "difference", "details", "logged_at"]
BILLABLE = {"completed", "shipped"}
SEVERITY = {
    "MISSING_PAYMENT": "high",
    "AMOUNT_MISMATCH": "high",
    "DUPLICATE_PAYMENT": "high",
    "ORPHAN_PAYMENT": "high",
    "PAYMENT_ON_CANCELLED_ORDER": "medium",
    "PAYMENT_FOR_REJECTED_ORDER": "medium",
    "PRICE_MISMATCH": "low",
}


@dataclass
class ReconciliationResult:
    orders: pd.DataFrame
    payments: pd.DataFrame
    exceptions: pd.DataFrame
    control_totals: dict = field(default_factory=dict)


def reconcile(orders: pd.DataFrame, payments: pd.DataFrame, products: pd.DataFrame,
              rejected_order_ids: set[str], batch_id: str, tolerance: float = 0.01,
              settlement_window_days: int = 2, as_of: str | None = None) -> ReconciliationResult:
    if as_of:
        as_of_date = date.fromisoformat(as_of)
    elif len(orders):
        as_of_date = date.fromisoformat(str(orders["order_date"].max()))
    else:
        as_of_date = date.today()
    orders = orders.copy()
    payments = payments.copy()
    logged_at = utc_now()
    exceptions: list[dict] = []

    def add(kind, order_id=None, payment_id=None, expected=None, actual=None, details=""):
        diff = None if expected is None or actual is None else round(actual - expected, 2)
        exceptions.append({
            "batch_id": batch_id, "exception_type": kind, "severity": SEVERITY[kind],
            "order_id": order_id, "payment_id": payment_id,
            "expected_amount": expected, "actual_amount": actual, "difference": diff,
            "details": details, "logged_at": logged_at,
        })

    # only successful payments count. failed attempts before a successful retry are normal
    # TODO: refunds should net off against the original payment instead of being ignored
    settled = payments[payments["status"] == "success"]
    per_order = (settled.groupby("order_id")
                 .agg(paid_amount=("amount", "sum"), payment_count=("payment_id", "count"),
                      payment_ids=("payment_id", lambda s: ",".join(sorted(s))))
                 .reset_index())
    merged = orders.merge(per_order, on="order_id", how="left")
    merged["payment_count"] = merged["payment_count"].fillna(0).astype(int)
    merged["paid_amount"] = merged["paid_amount"].fillna(0.0).round(2)

    # ---- order-level checks
    order_status: dict[str, str] = {}
    for row in merged.itertuples(index=False):
        expected, paid = float(row.order_amount), float(row.paid_amount)
        if row.status in BILLABLE:
            if row.payment_count == 0:
                age_days = (as_of_date - date.fromisoformat(str(row.order_date))).days
                if age_days <= settlement_window_days:
                    order_status[row.order_id] = "AWAITING_SETTLEMENT"
                else:
                    add("MISSING_PAYMENT", row.order_id, None, expected, 0.0,
                        f"{row.status} order has no successful payment {age_days} days after the order")
                    order_status[row.order_id] = "MISSING_PAYMENT"
            elif row.payment_count > 1:
                add("DUPLICATE_PAYMENT", row.order_id, row.payment_ids, expected, paid,
                    f"{row.payment_count} successful payments for one order")
                order_status[row.order_id] = "DUPLICATE_PAYMENT"
            elif abs(paid - expected) > tolerance:
                add("AMOUNT_MISMATCH", row.order_id, row.payment_ids, expected, paid,
                    "payment amount differs from order amount")
                order_status[row.order_id] = "AMOUNT_MISMATCH"
            else:
                order_status[row.order_id] = "MATCHED"
        elif row.status == "cancelled":
            if row.payment_count > 0:
                add("PAYMENT_ON_CANCELLED_ORDER", row.order_id, row.payment_ids, 0.0, paid,
                    "cancelled order was charged; refund likely required")
                order_status[row.order_id] = "PAYMENT_ON_CANCELLED_ORDER"
            else:
                order_status[row.order_id] = "NOT_BILLABLE"
        else:  # pending
            order_status[row.order_id] = "MATCHED" if row.payment_count == 1 and abs(paid - expected) <= tolerance \
                else "AWAITING_PAYMENT"

    # ---- catalog price check
    priced = orders.merge(products[["product_id", "list_price"]], on="product_id", how="left")
    for row in priced[(priced["unit_price"] - priced["list_price"]).abs() > tolerance].itertuples(index=False):
        add("PRICE_MISMATCH", row.order_id, None, float(row.list_price), float(row.unit_price),
            f"sold at {row.unit_price:.2f} vs catalog {row.list_price:.2f} for {row.product_id}")

    # ---- payment-level checks
    valid_order_ids = set(orders["order_id"])
    dup_orders = {oid for oid, s in order_status.items() if s == "DUPLICATE_PAYMENT"}
    mismatch_orders = {oid for oid, s in order_status.items() if s == "AMOUNT_MISMATCH"}
    payment_status = []
    for row in payments.itertuples(index=False):
        if row.order_id not in valid_order_ids:
            if row.status == "success":
                kind = "PAYMENT_FOR_REJECTED_ORDER" if row.order_id in rejected_order_ids else "ORPHAN_PAYMENT"
                detail = ("order exists in source but failed validation" if kind == "PAYMENT_FOR_REJECTED_ORDER"
                          else "order id not found in any source")
                add(kind, row.order_id, row.payment_id, 0.0, float(row.amount), detail)
                payment_status.append(kind)
            else:
                payment_status.append("UNMATCHED_NOT_SETTLED")
        elif row.status != "success":
            payment_status.append("NOT_SETTLED")
        elif row.order_id in dup_orders:
            payment_status.append("DUPLICATE_PAYMENT")
        elif row.order_id in mismatch_orders:
            payment_status.append("AMOUNT_MISMATCH")
        elif order_status.get(row.order_id) == "PAYMENT_ON_CANCELLED_ORDER":
            payment_status.append("PAYMENT_ON_CANCELLED_ORDER")
        else:
            payment_status.append("MATCHED")

    orders["reconciliation_status"] = orders["order_id"].map(order_status)
    payments["reconciliation_status"] = payment_status

    # ---- control totals
    expected_revenue = round(float(orders.loc[orders["status"].isin(BILLABLE), "order_amount"].sum()), 2)
    in_window = round(float(orders.loc[orders["reconciliation_status"] == "AWAITING_SETTLEMENT",
                                       "order_amount"].sum()), 2)
    settled_linked = round(float(settled.loc[settled["order_id"].isin(valid_order_ids), "amount"].sum()), 2)
    settled_unlinked = round(float(settled.loc[~settled["order_id"].isin(valid_order_ids), "amount"].sum()), 2)
    control_totals = {
        "expected_revenue_billable_orders": expected_revenue,
        "within_settlement_window": in_window,
        "expected_revenue_due": round(expected_revenue - in_window, 2),
        "settled_payments_on_valid_orders": settled_linked,
        "settled_payments_unmatched": settled_unlinked,
        "net_difference": round(settled_linked - (expected_revenue - in_window), 2),
    }

    exceptions_df = pd.DataFrame(exceptions, columns=EXCEPTION_COLUMNS)
    return ReconciliationResult(orders, payments, exceptions_df, control_totals)
