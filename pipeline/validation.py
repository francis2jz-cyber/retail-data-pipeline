"""Validation rules.

Each Rule returns a mask of the rows that FAIL it. Any row that fails something goes
to the error table (one row per rule broken) with the original record as JSON, and
everything else carries on.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

import pandas as pd

from pipeline.db import utc_now

ERROR_COLUMNS = ["batch_id", "source", "record_key", "rule", "column_name",
                 "invalid_value", "error_message", "raw_record", "logged_at"]

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"
ORDER_STATUSES = {"completed", "shipped", "pending", "cancelled"}
PAYMENT_STATUSES = {"success", "failed", "pending", "refunded"}
PAYMENT_METHODS = {"card", "eft", "paypal", "wallet"}


@dataclass(frozen=True)
class Rule:
    name: str
    column: str
    check: Callable[[pd.DataFrame], pd.Series]
    message: str


@dataclass
class ValidationResult:
    source: str
    valid: pd.DataFrame
    invalid: pd.DataFrame
    errors: pd.DataFrame


# ---------------------------------------------------------------- helpers
def _text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _blank(series: pd.Series) -> pd.Series:
    return _text(series).eq("")


# ---------------------------------------------------------------- rule factories
def not_null(col: str) -> Rule:
    return Rule("not_null", col, lambda df: _blank(df[col]), f"{col} is required")


def unique(col: str) -> Rule:
    return Rule("duplicate_key", col,
                lambda df: ~_blank(df[col]) & _text(df[col]).duplicated(keep="first"),
                f"{col} appears more than once; first occurrence kept")


def matches(col: str, pattern: str, label: str) -> Rule:
    return Rule(f"invalid_{label}", col,
                lambda df: ~_blank(df[col]) & ~_text(df[col]).str.match(pattern),
                f"{col} is not a valid {label}")


def is_date(col: str, fmt: str = "%Y-%m-%d") -> Rule:
    def check(df: pd.DataFrame) -> pd.Series:
        parsed = pd.to_datetime(_text(df[col]), format=fmt, errors="coerce")
        return ~_blank(df[col]) & parsed.isna()
    return Rule("invalid_date", col, check, f"{col} is not a valid date ({fmt})")


def is_number(col: str, minimum: float | None = None, exclusive: bool = False, integer: bool = False) -> Rule:
    def check(df: pd.DataFrame) -> pd.Series:
        num = pd.to_numeric(_text(df[col]), errors="coerce")
        bad = num.isna()
        if integer:
            bad |= num.notna() & (num % 1 != 0)
        if minimum is not None:
            bad |= (num <= minimum) if exclusive else (num < minimum)
        return ~_blank(df[col]) & bad
    bound = "" if minimum is None else f" {'>' if exclusive else '>='} {minimum}"
    kind = "an integer" if integer else "a number"
    return Rule("invalid_number", col, check, f"{col} must be {kind}{bound}")


def one_of(col: str, allowed: set[str]) -> Rule:
    return Rule("invalid_value", col,
                lambda df: ~_blank(df[col]) & ~_text(df[col]).str.lower().isin(allowed),
                f"{col} must be one of {sorted(allowed)}")


def references(col: str, valid_keys: set[str], entity: str) -> Rule:
    return Rule("unknown_reference", col,
                lambda df: ~_blank(df[col]) & ~_text(df[col]).str.upper().isin(valid_keys),
                f"{col} does not match any valid {entity}")


# ---------------------------------------------------------------- rule sets
CUSTOMER_RULES = [
    not_null("customer_id"), unique("customer_id"),
    not_null("first_name"), not_null("last_name"),
    not_null("email"), matches("email", EMAIL_PATTERN, "email"),
    not_null("country"), matches("country", r"^[A-Za-z]{2}$", "country_code"),
    not_null("signup_date"), is_date("signup_date"),
]

PRODUCT_RULES = [
    not_null("product_id"), unique("product_id"),
    not_null("product_name"), not_null("category"),
    not_null("unit_price"), is_number("unit_price", minimum=0, exclusive=True),
    not_null("stock_quantity"), is_number("stock_quantity", minimum=0, integer=True),
    is_date("last_updated"),
]


def order_rules(valid_customer_ids: set[str], valid_product_ids: set[str]) -> list[Rule]:
    return [
        not_null("order_id"), unique("order_id"),
        not_null("customer_id"), references("customer_id", valid_customer_ids, "customer"),
        not_null("product_id"), references("product_id", valid_product_ids, "product"),
        not_null("quantity"), is_number("quantity", minimum=0, exclusive=True, integer=True),
        not_null("unit_price"), is_number("unit_price", minimum=0, exclusive=True),
        not_null("order_date"), is_date("order_date"),
        not_null("status"), one_of("status", ORDER_STATUSES),
    ]


def payment_rules(currencies: set[str]) -> list[Rule]:
    return [
        not_null("payment_id"), unique("payment_id"),
        not_null("order_id"),
        not_null("amount"), is_number("amount", minimum=0, exclusive=True),
        not_null("currency"), one_of("currency", {c.lower() for c in currencies}),
        not_null("payment_method"), one_of("payment_method", PAYMENT_METHODS),
        not_null("status"), one_of("status", PAYMENT_STATUSES),
        not_null("paid_at"), is_date("paid_at", fmt="ISO8601"),
    ]


# ---------------------------------------------------------------- engine
def validate(df: pd.DataFrame, source: str, key_column: str, rules: list[Rule], batch_id: str) -> ValidationResult:
    df = df.reset_index(drop=True)
    failed = pd.Series(False, index=df.index)
    errors: list[dict] = []
    logged_at = utc_now()

    for rule in rules:
        mask = rule.check(df).fillna(False).astype(bool)
        for idx in df.index[mask]:
            row = df.loc[idx]
            errors.append({
                "batch_id": batch_id,
                "source": source,
                "record_key": str(row[key_column]),
                "rule": rule.name,
                "column_name": rule.column,
                "invalid_value": str(row[rule.column]),
                "error_message": rule.message,
                "raw_record": json.dumps({k: str(v) for k, v in row.items()}),
                "logged_at": logged_at,
            })
        failed |= mask

    return ValidationResult(
        source=source,
        valid=df[~failed].reset_index(drop=True),
        invalid=df[failed].reset_index(drop=True),
        errors=pd.DataFrame(errors, columns=ERROR_COLUMNS),
    )


# Order matters: orders are checked against customers/products that PASSED, otherwise
# the foreign keys in fact_orders would blow up on load.
def validate_all(raw: dict[str, pd.DataFrame], batch_id: str,
                 currencies: set[str] = frozenset({"USD"})) -> dict[str, ValidationResult]:
    customers = validate(raw["customers"], "customers", "customer_id", CUSTOMER_RULES, batch_id)
    products = validate(raw["products"], "products", "product_id", PRODUCT_RULES, batch_id)
    valid_customer_ids = set(_text(customers.valid["customer_id"]).str.upper())
    valid_product_ids = set(_text(products.valid["product_id"]).str.upper())
    orders = validate(raw["orders"], "orders", "order_id",
                      order_rules(valid_customer_ids, valid_product_ids), batch_id)
    payments = validate(raw["payments"], "payments", "payment_id", payment_rules(set(currencies)), batch_id)
    return {"customers": customers, "products": products, "orders": orders, "payments": payments}
