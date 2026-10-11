"""Cleaning and typing. Validation has already run, so none of the casts here should fail."""
from __future__ import annotations

import pandas as pd


def _clean(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.replace(r"\s+", " ", regex=True)


def _name(series: pd.Series) -> pd.Series:
    return _clean(series).str.title()


def _iso_date(series: pd.Series, fmt: str = "%Y-%m-%d") -> pd.Series:
    return pd.to_datetime(_clean(series), format=fmt).dt.strftime("%Y-%m-%d")


def _money(series: pd.Series) -> pd.Series:
    return pd.to_numeric(_clean(series)).astype(float).round(2)


def transform_customers(df: pd.DataFrame, batch_id: str) -> pd.DataFrame:
    first, last = _name(df["first_name"]), _name(df["last_name"])
    return pd.DataFrame({
        "customer_id": _clean(df["customer_id"]).str.upper(),
        "first_name": first,
        "last_name": last,
        "full_name": first + " " + last,
        "email": _clean(df["email"]).str.lower(),
        "country": _clean(df["country"]).str.upper(),
        "signup_date": _iso_date(df["signup_date"]),
        "_batch_id": batch_id,
    })


def transform_products(df: pd.DataFrame, batch_id: str) -> pd.DataFrame:
    return pd.DataFrame({
        "product_id": _clean(df["product_id"]).str.upper(),
        "product_name": _clean(df["product_name"]),
        "category": _name(df["category"]),
        "list_price": _money(df["unit_price"]),
        "stock_quantity": pd.to_numeric(_clean(df["stock_quantity"])).astype(int),
        "last_updated": _iso_date(df["last_updated"]),
        "_batch_id": batch_id,
    })


def transform_orders(df: pd.DataFrame, batch_id: str) -> pd.DataFrame:
    quantity = pd.to_numeric(_clean(df["quantity"])).astype(int)
    unit_price = _money(df["unit_price"])
    order_date = _iso_date(df["order_date"])
    return pd.DataFrame({
        "order_id": _clean(df["order_id"]).str.upper(),
        "customer_id": _clean(df["customer_id"]).str.upper(),
        "product_id": _clean(df["product_id"]).str.upper(),
        "quantity": quantity,
        "unit_price": unit_price,
        "order_amount": (quantity * unit_price).round(2),
        "order_date": order_date,
        "order_month": order_date.str.slice(0, 7),
        "status": _clean(df["status"]).str.lower(),
        "_batch_id": batch_id,
    })


def transform_payments(df: pd.DataFrame, batch_id: str) -> pd.DataFrame:
    paid_at = pd.to_datetime(_clean(df["paid_at"]), format="ISO8601", utc=True)
    return pd.DataFrame({
        "payment_id": _clean(df["payment_id"]).str.upper(),
        "order_id": _clean(df["order_id"]).str.upper(),
        "amount": _money(df["amount"]),
        "currency": _clean(df["currency"]).str.upper(),
        "payment_method": _clean(df["payment_method"]).str.lower(),
        "status": _clean(df["status"]).str.lower(),
        "paid_at": paid_at.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "paid_date": paid_at.dt.strftime("%Y-%m-%d"),
        "_batch_id": batch_id,
    })


def transform_all(valid: dict[str, pd.DataFrame], batch_id: str) -> dict[str, pd.DataFrame]:
    return {
        "customers": transform_customers(valid["customers"], batch_id),
        "products": transform_products(valid["products"], batch_id),
        "orders": transform_orders(valid["orders"], batch_id),
        "payments": transform_payments(valid["payments"], batch_id),
    }
