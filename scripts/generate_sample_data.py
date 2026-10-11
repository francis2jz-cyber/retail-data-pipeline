"""Generates the sample data, with problems planted in it on purpose.

Writes customers / inventory / orders CSVs to data/raw, the payments the mock API
serves to data/api/payments.json, and defect_manifest.json listing everything that
was planted. The tests use the manifest to check the pipeline catches exactly those.

It's seeded, so the output is the same every time:
    python scripts/generate_sample_data.py
    python scripts/generate_sample_data.py --orders 5000 --seed 7
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

FIRST_NAMES = ["Amara", "Liam", "Sipho", "Olivia", "Noah", "Thandi", "Ethan", "Zanele", "Mia", "Lucas",
               "Aisha", "James", "Naledi", "Sofia", "Daniel", "Chloe", "Kwame", "Isla", "Mateo", "Priya"]
LAST_NAMES = ["Smith", "Naidoo", "Dlamini", "Johnson", "Okafor", "Brown", "Mokoena", "Garcia", "Patel",
              "Williams", "O'Brien", "Nkosi", "Muller", "Rossi", "Khumalo", "Taylor", "Chen", "Botha", "Silva", "Adeyemi"]
COUNTRIES = ["US", "GB", "DE", "FR", "CA", "AU", "ZA", "NG", "IN", "BR"]
CATALOG = {
    "Electronics": ["Wireless Earbuds", "USB-C Hub", "Bluetooth Speaker", "Smart Watch", "Webcam HD", "Power Bank", "Mechanical Keyboard", "Gaming Mouse"],
    "Home": ["Coffee Grinder", "Desk Lamp", "Throw Blanket", "Ceramic Mug Set", "Air Purifier", "Wall Clock", "Plant Pot", "Knife Set"],
    "Sports": ["Yoga Mat", "Resistance Bands", "Water Bottle", "Running Belt", "Jump Rope", "Foam Roller", "Dumbbell Pair", "Cycling Gloves"],
    "Books": ["Data Engineering Basics", "SQL Cookbook", "Python Tricks", "Clean Architecture", "Statistics 101", "The Pragmatic Coder", "Designing Pipelines", "Analytics Handbook"],
    "Beauty": ["Face Serum", "Lip Balm", "Hair Oil", "Sunscreen SPF50", "Body Lotion", "Shampoo Bar", "Clay Mask", "Hand Cream"],
}
ORDER_STATUSES = ["completed", "shipped", "pending", "cancelled"]
ORDER_STATUS_WEIGHTS = [0.62, 0.18, 0.10, 0.10]
PAYMENT_METHODS = ["card", "card", "card", "eft", "paypal", "wallet"]
AWAITING_SETTLEMENT_DATES = ["2025-12-31", "2025-12-31", "2025-12-30", "2025-12-30", "2025-12-29"]
SETTLEMENT_SAFE_DATE = "2025-12-20"


def _rand_date(rng: random.Random, start: date, end: date) -> date:
    return start + timedelta(days=rng.randint(0, (end - start).days))


def _messy(rng: random.Random, value: str) -> str:
    """Make formatting inconsistent (casing/whitespace) without making it invalid."""
    roll = rng.random()
    if roll < 0.08:
        return value.upper()
    if roll < 0.16:
        return value.lower()
    if roll < 0.22:
        return f"  {value} "
    return value


def _take(pool: list, n: int, rng: random.Random) -> list:
    picked = rng.sample(pool, n)
    for item in picked:
        pool.remove(item)
    return picked


def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def generate(raw_dir: Path, api_dir: Path, n_customers: int = 200, n_products: int = 40,
             n_orders: int = 1500, seed: int = 42) -> dict:
    rng = random.Random(seed)
    raw_dir.mkdir(parents=True, exist_ok=True)
    api_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- customers
    customers = []
    for i in range(1, n_customers + 1):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        email = f"{first}.{last.replace(chr(39), '')}{i}@example.com".lower()
        customers.append({
            "customer_id": f"C{i:04d}",
            "first_name": _messy(rng, first),
            "last_name": _messy(rng, last),
            "email": email.upper() if rng.random() < 0.1 else email,
            "country": rng.choice(COUNTRIES).lower() if rng.random() < 0.1 else rng.choice(COUNTRIES),
            "signup_date": _rand_date(rng, date(2023, 1, 1), date(2024, 12, 31)).isoformat(),
        })

    pool = list(range(n_customers))
    bad_customers: set[str] = set()
    for idx in _take(pool, 3, rng):
        customers[idx]["email"] = ""
        bad_customers.add(customers[idx]["customer_id"])
    for idx, bad in zip(_take(pool, 3, rng), ["john.smith@", "no-at-sign.example.com", "two@@example.com"]):
        customers[idx]["email"] = bad
        bad_customers.add(customers[idx]["customer_id"])
    for idx in _take(pool, 1, rng):
        customers[idx]["signup_date"] = "2024-02-30"
        bad_customers.add(customers[idx]["customer_id"])
    for idx in _take(pool, 1, rng):
        customers[idx]["last_name"] = ""
        bad_customers.add(customers[idx]["customer_id"])
    customer_duplicates = [dict(customers[i]) for i in rng.sample(pool, 2)]
    customers.extend(customer_duplicates)
    rng.shuffle(customers)
    clean_customer_ids = sorted({c["customer_id"] for c in customers} - bad_customers)

    # ------------------------------------------------------------- inventory
    products = []
    all_items = [(cat, name) for cat, names in CATALOG.items() for name in names]
    for i, (category, name) in enumerate(rng.sample(all_items, n_products), start=1):
        products.append({
            "product_id": f"P{i:03d}",
            "product_name": name,
            "category": category,
            "unit_price": f"{rng.uniform(5, 450):.2f}",
            "stock_quantity": str(rng.randint(0, 500)),
            "last_updated": _rand_date(rng, date(2025, 11, 1), date(2025, 12, 31)).isoformat(),
        })
    pool = list(range(n_products))
    bad_products: set[str] = set()
    for idx in _take(pool, 1, rng):
        products[idx]["unit_price"] = "-19.99"
        bad_products.add(products[idx]["product_id"])
    for idx in _take(pool, 1, rng):
        products[idx]["category"] = ""
        bad_products.add(products[idx]["product_id"])
    for idx in _take(pool, 1, rng):
        products[idx]["stock_quantity"] = "lots"
        bad_products.add(products[idx]["product_id"])
    products.append(dict(products[rng.choice(pool)]))
    price_lookup = {p["product_id"]: float(p["unit_price"]) for p in products}
    clean_product_ids = sorted({p["product_id"] for p in products} - bad_products)

    # ------------------------------------------------------------- orders
    orders = []
    for i in range(1, n_orders + 1):
        pid = rng.choice(clean_product_ids)
        orders.append({
            "order_id": f"O{i:05d}",
            "customer_id": rng.choice(clean_customer_ids),
            "product_id": pid,
            "quantity": str(rng.randint(1, 5)),
            "unit_price": f"{price_lookup[pid]:.2f}",
            "order_date": _rand_date(rng, date(2025, 1, 1), date(2025, 12, 31)).isoformat(),
            "status": rng.choices(ORDER_STATUSES, ORDER_STATUS_WEIGHTS)[0],
        })

    pool = list(range(n_orders))
    unknown_customer = _take(pool, 5, rng)
    unknown_product = _take(pool, 4, rng)
    bad_quantity = _take(pool, 6, rng)
    bad_date = _take(pool, 3, rng)
    bad_status = _take(pool, 2, rng)
    for idx in unknown_customer:
        orders[idx]["customer_id"] = "C9999"
    for idx in unknown_product:
        orders[idx]["product_id"] = "P999"
    for idx, qty in zip(bad_quantity, ["0", "-1", "-2", "0", "-3", "abc"]):
        orders[idx]["quantity"] = qty
    for idx, value in zip(bad_date, ["2025-13-01", "not a date", ""]):
        orders[idx]["order_date"] = value
    for idx in bad_status:
        orders[idx]["status"] = "lost"

    # Reconciliation scenarios are drawn from otherwise-clean orders.
    paid_pool = [i for i in pool if orders[i]["status"] in ("completed", "shipped")]
    cancelled_pool = [i for i in pool if orders[i]["status"] == "cancelled"]
    missing_payment = set(_take(paid_pool, 12, rng))
    amount_mismatch = set(_take(paid_pool, 10, rng))
    duplicate_payment = set(_take(paid_pool, 6, rng))
    price_mismatch = set(_take(paid_pool, 15, rng))
    failed_then_success = set(_take(paid_pool, 4, rng))
    paid_cancelled = set(_take(cancelled_pool, 3, rng))

    # Settlement-window scenarios use their own random stream, so adding them does not
    # reshuffle any other planted defect in the committed sample data.
    timing_rng = random.Random(seed * 7919 + 1)
    for idx in missing_payment:  # genuinely missing payments are well past any settlement window
        if orders[idx]["order_date"] > SETTLEMENT_SAFE_DATE:
            orders[idx]["order_date"] = _rand_date(timing_rng, date(2025, 1, 1),
                                                   date.fromisoformat(SETTLEMENT_SAFE_DATE)).isoformat()
    for idx in price_mismatch:  # sold at a discount vs catalog price
        orders[idx]["unit_price"] = f"{float(orders[idx]['unit_price']) * 0.9:.2f}"
    for idx in rng.sample(range(n_orders), 40):  # cosmetic mess, still valid after cleaning
        if orders[idx]["status"] != "lost":
            orders[idx]["status"] = _messy(rng, orders[idx]["status"])

    order_duplicates = [dict(orders[i]) for i in rng.sample(pool, 2)]
    rejected_order_idx = set(unknown_customer + unknown_product + bad_quantity + bad_date + bad_status)

    # ------------------------------------------------------------- payments
    payments: list[dict] = []
    payment_counter = 0

    def add_payment(order_id: str, amount, when: datetime, status: str = "success", currency: str = "USD") -> dict:
        nonlocal payment_counter
        payment_counter += 1
        record = {
            "payment_id": f"PAY{payment_counter:06d}",
            "order_id": order_id,
            "amount": amount,
            "currency": currency,
            "payment_method": rng.choice(PAYMENT_METHODS),
            "status": status,
            "paid_at": when.strftime("%Y-%m-%dT%H:%M:%SZ") if isinstance(when, datetime) else when,
        }
        payments.append(record)
        return record

    payments_for_rejected_orders = 0
    for idx, order in enumerate(orders):
        status = order["status"].strip().lower()
        if idx in bad_quantity or idx in bad_date or idx in bad_status:
            continue
        try:
            when = datetime.fromisoformat(order["order_date"]) + timedelta(hours=rng.randint(0, 48), minutes=rng.randint(0, 59))
        except ValueError:
            continue
        total = round(int(order["quantity"]) * float(order["unit_price"]), 2)

        if status in ("completed", "shipped"):
            if idx in missing_payment:
                continue
            if idx in failed_then_success:
                add_payment(order["order_id"], total, when - timedelta(minutes=5), status="failed")
            amount = total
            if idx in amount_mismatch:
                amount = round(total + rng.choice([-1, 1]) * rng.uniform(0.5, 25), 2)
            add_payment(order["order_id"], amount, when)
            if idx in duplicate_payment:
                add_payment(order["order_id"], total, when + timedelta(minutes=2))
            if idx in rejected_order_idx:
                payments_for_rejected_orders += 1
        elif status == "pending" and rng.random() < 0.5:
            add_payment(order["order_id"], total, when, status="pending")
        elif status == "cancelled" and idx in paid_cancelled:
            add_payment(order["order_id"], total, when)

    for n in range(8):  # payments for orders that don't exist anywhere
        add_payment(f"O9{n:04d}", round(rng.uniform(10, 300), 2),
                    datetime(2025, rng.randint(1, 12), rng.randint(1, 28), rng.randint(0, 23)))

    # Payment records that fail validation (extra noise records, not tied to recon scenarios)
    valid_order_ids = [orders[i]["order_id"] for i in pool]
    some_time = datetime(2025, 6, 1, 12, 0)
    add_payment(rng.choice(valid_order_ids), None, some_time, status="failed")
    add_payment(rng.choice(valid_order_ids), None, some_time, status="failed")
    add_payment(rng.choice(valid_order_ids), -50.0, some_time, status="failed")
    add_payment(rng.choice(valid_order_ids), -12.5, some_time, status="failed")
    add_payment(rng.choice(valid_order_ids), 40.0, some_time, status="failed", currency="XYZ")
    add_payment(rng.choice(valid_order_ids), 40.0, some_time, status="failed", currency="XYZ")
    add_payment(rng.choice(valid_order_ids), 40.0, "yesterday", status="failed")
    add_payment(rng.choice(valid_order_ids), 40.0, "2025-02-31T10:00:00Z", status="failed")
    payments.append(dict(rng.choice(payments[:-8])))  # exact duplicate payment_id

    orders.extend(order_duplicates)
    rng.shuffle(orders)
    rng.shuffle(payments)

    # Orders placed in the last days of the extract whose payment hasn't landed yet.
    # They should be tagged AWAITING_SETTLEMENT, not flagged as missing payments.
    for k, day in enumerate(AWAITING_SETTLEMENT_DATES, start=1):
        pid = timing_rng.choice(clean_product_ids)
        late = {
            "order_id": f"O{n_orders + k:05d}",
            "customer_id": timing_rng.choice(clean_customer_ids),
            "product_id": pid,
            "quantity": str(timing_rng.randint(1, 5)),
            "unit_price": f"{price_lookup[pid]:.2f}",
            "order_date": day,
            "status": timing_rng.choice(["completed", "shipped"]),
        }
        orders.insert(timing_rng.randint(0, len(orders)), late)

    # ------------------------------------------------------------- write
    _write_csv(raw_dir / "customers.csv", customers,
               ["customer_id", "first_name", "last_name", "email", "country", "signup_date"])
    _write_csv(raw_dir / "inventory.csv", products,
               ["product_id", "product_name", "category", "unit_price", "stock_quantity", "last_updated"])
    _write_csv(raw_dir / "orders.csv", orders,
               ["order_id", "customer_id", "product_id", "quantity", "unit_price", "order_date", "status"])
    (api_dir / "payments.json").write_text(json.dumps(payments, indent=1), encoding="utf-8")

    manifest = {
        "seed": seed,
        "row_counts": {"customers": len(customers), "products": len(products),
                       "orders": len(orders), "payments": len(payments)},
        "expected_rejected_records": {
            "customers": 3 + 3 + 1 + 1 + 2,
            "products": 3 + 1,
            "orders": 5 + 4 + 6 + 3 + 2 + 2,
            "payments": 2 + 2 + 2 + 2 + 1,
        },
        "expected_reconciliation_exceptions": {
            "MISSING_PAYMENT": len(missing_payment),
            "AMOUNT_MISMATCH": len(amount_mismatch),
            "DUPLICATE_PAYMENT": len(duplicate_payment),
            "PAYMENT_ON_CANCELLED_ORDER": len(paid_cancelled),
            "PRICE_MISMATCH": len(price_mismatch),
            "ORPHAN_PAYMENT": 8,
            "PAYMENT_FOR_REJECTED_ORDER": payments_for_rejected_orders,
        },
        "expected_awaiting_settlement_orders": len(AWAITING_SETTLEMENT_DATES),
        "extract_cutoff_date": max(AWAITING_SETTLEMENT_DATES),
    }
    (raw_dir / "defect_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--customers", type=int, default=200)
    parser.add_argument("--products", type=int, default=40)
    parser.add_argument("--orders", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    manifest = generate(PROJECT_ROOT / "data" / "raw", PROJECT_ROOT / "data" / "api",
                        args.customers, args.products, args.orders, args.seed)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
