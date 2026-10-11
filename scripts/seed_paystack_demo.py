"""Seed your Paystack TEST account with payments that match a demo order set.

What it does
  1. Generates a smaller demo dataset in data/paystack_demo/ (same planted defects:
     missing payments, duplicates, wrong amounts, orphans, charges on cancelled orders).
  2. Finds a reusable test card authorization on your account. If there is none, it
     creates a checkout link: open it, pay with a Paystack test card, and run this again.
  3. Replays every successful demo payment into Paystack with charge_authorization,
     carrying the order id in metadata. References are deterministic, so re-running
     the script never creates duplicates.

Then run the pipeline against the real API:
    python run_pipeline.py --payment-source paystack

Requirements: PAYSTACK_SECRET_KEY=sk_test_... in .env. Live keys are refused.

Usage:
    python scripts/seed_paystack_demo.py
    python scripts/seed_paystack_demo.py --orders 200 --currency ZAR
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.config import PROJECT_ROOT, Settings  # noqa: E402
from pipeline.ingestion import IngestionError  # noqa: E402
from pipeline.paystack import list_transactions, make_session  # noqa: E402
from scripts.generate_sample_data import generate  # noqa: E402

DEMO_DIR = PROJECT_ROOT / "data" / "paystack_demo"
TEST_PAYMENTS_DOCS = "https://paystack.com/docs/payments/test-payments/"


def find_reusable_authorization(session, base_url: str) -> tuple[str, str] | None:
    for txn in list_transactions(session, base_url, per_page=100):
        auth = txn.get("authorization") or {}
        email = (txn.get("customer") or {}).get("email")
        if txn.get("status") == "success" and auth.get("reusable") and auth.get("authorization_code") and email:
            return auth["authorization_code"], email
    return None


def create_checkout_link(session, base_url: str, currency: str) -> str:
    response = session.post(f"{base_url}/transaction/initialize", timeout=20, data=json.dumps({
        "email": "pipeline-demo@example.com", "amount": "10000", "currency": currency,
        "metadata": json.dumps({"purpose": "create reusable test authorization"}),
    }))
    payload = response.json()
    if not payload.get("status"):
        raise IngestionError(f"Could not create a checkout link: {payload.get('message')}")
    return payload["data"]["authorization_url"]


def charge(session, base_url: str, body: dict, max_retries: int = 4) -> str:
    """Returns 'created', 'exists' or raises."""
    for attempt in range(1, max_retries + 1):
        response = session.post(f"{base_url}/transaction/charge_authorization", data=json.dumps(body), timeout=30)
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        payload = response.json()
        if payload.get("status"):
            return "created"
        message = str(payload.get("message", ""))
        if "duplicate" in message.lower():
            return "exists"
        raise IngestionError(f"Paystack rejected charge {body['reference']}: {message}")
    raise IngestionError(f"Paystack kept failing for {body['reference']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--orders", type=int, default=150, help="Number of demo orders (default 150)")
    parser.add_argument("--currency", default=None, help="Charge currency (default: BASE_CURRENCY or ZAR)")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--delay", type=float, default=0.25, help="Seconds between API calls")
    args = parser.parse_args(argv)

    settings = Settings()
    currency = (args.currency or (settings.base_currency if settings.base_currency != "USD" else "ZAR")).upper()
    base_url = settings.paystack_base_url.rstrip("/")
    try:
        session = make_session(settings.paystack_secret_key)
        manifest = generate(DEMO_DIR / "raw", DEMO_DIR / "api", n_customers=60, n_products=20,
                            n_orders=args.orders, seed=args.seed)
        print(f"Demo orders written to {DEMO_DIR / 'raw'}")

        found = find_reusable_authorization(session, base_url)
        if not found:
            link = create_checkout_link(session, base_url, currency)
            print("\nNo reusable test card found on your Paystack test account yet. One-time step:")
            print(f"  1. Open: {link}")
            print(f"  2. Pay with a Paystack test card (see {TEST_PAYMENTS_DOCS})")
            print("  3. Run this script again.\n")
            return 0
        auth_code, email = found

        payments = json.loads((DEMO_DIR / "api" / "payments.json").read_text(encoding="utf-8"))
        to_send = [p for p in payments if p.get("status") == "success" and isinstance(p.get("amount"), (int, float))
                   and p["amount"] > 0]
        tag = f"demo{args.seed}"
        created = existing = 0
        for i, p in enumerate(to_send, start=1):
            result = charge(session, base_url, {
                "email": email,
                "amount": str(round(p["amount"] * 100)),
                "currency": currency,
                "authorization_code": auth_code,
                "reference": f"{p['payment_id']}-{tag}",
                "metadata": json.dumps({"order_id": p["order_id"], "source": "retail-data-pipeline demo"}),
            })
            created += result == "created"
            existing += result == "exists"
            print(f"\r  {i}/{len(to_send)} payments sent ({created} new, {existing} already there)", end="")
            time.sleep(args.delay)
        print("\n")
    except (IngestionError, requests.RequestException) as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        return 1

    print("Done. Expected reconciliation exceptions for this demo set:")
    for kind, count in manifest["expected_reconciliation_exceptions"].items():
        print(f"  {kind:<28} {count}")
    print("\nAdd these lines to .env (or keep them for a Paystack run):")
    print("  PAYMENT_SOURCE=paystack")
    print(f"  BASE_CURRENCY={currency}")
    print("  RAW_DATA_DIR=data/paystack_demo/raw")
    print("\nThen run:  python run_pipeline.py")
    print("Note: other transactions already on your test account (like the checkout payment)")
    print("will also be pulled in and reported, just as they would be in a real business.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
