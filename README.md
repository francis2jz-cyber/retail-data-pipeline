# Retail data pipeline

![CI](https://github.com/francis2jz-cyber/retail-data-pipeline/actions/workflows/ci.yml/badge.svg)

A batch pipeline in Python and SQL. It pulls orders, customers and inventory from CSV files and
payments from an API, checks everything, puts bad rows in an error table, loads the clean data into
SQLite or Postgres, and then **reconciles orders against payments**: did every order get paid, did
anyone get charged twice, are there payments that don't belong to any order?

I built it to practise the parts of data engineering that most tutorials skip: what to do with bad
records, and how to prove two systems actually agree with each other.

There's a longer write-up with the business side of it in
[docs/Retail_Data_Pipeline_Overview.pdf](docs/Retail_Data_Pipeline_Overview.pdf).

## Why

Most pipeline projects I came across stop once the data is loaded. In a real business that's where
the questions start. The payment provider and the order system never agree perfectly, and somebody
usually ends up matching them by hand in Excel at month end.

I also wanted it to be testable properly. The sample data has known problems planted in it (bad
emails, duplicate ids, impossible dates, missing payments, double charges, orphan payments...) and
the tests check that the pipeline finds every one of them and nothing else.

## How it works

```mermaid
flowchart TD
    A[Orders CSV] --> I
    B[Customers CSV] --> I
    C[Payments API<br/>mock or Paystack] --> I
    D[Inventory CSV] --> I
    I[Ingestion] --> S[(Staging)]
    S --> V{Validation}
    V -- invalid --> E[(Error table)]
    V -- valid --> T[Transformation]
    T --> R{Reconciliation}
    R --> DB[(SQLite / Postgres)]
    R --> X[Exception report]
    DB --> Q[SQL analytics]
```

1. **Ingestion** (`pipeline/ingestion.py`) reads the CSVs and pages through the payments API, with
   retries. Everything is read as text so nothing gets silently converted.
2. **Staging** (`pipeline/staging.py`) stores each source exactly as it arrived, tagged with a
   batch id, so any number can be traced back to the raw row.
3. **Validation** (`pipeline/validation.py`) is a small rule engine: required fields, unique ids,
   email format, valid dates, numbers in range, allowed values, and references to customers and
   products that exist. Rows that fail go to `err_validation_errors` with the rule they broke and
   the original record.
4. **Transformation** (`pipeline/transformation.py`) cleans things up (trims, fixes casing, casts
   types) and works out order totals.
5. **Reconciliation** (`pipeline/reconciliation.py`) matches orders to payments and to catalog
   prices, and tags every order and payment with a status.
6. **Load** (`pipeline/loader.py`) writes the clean tables in one transaction, and
   `pipeline/reporting.py` writes the exception report.
7. **Analytics**: ten queries in `sql/analytics/` (monthly revenue with running totals, top
   customers, best seller per category, payment failure rates, etc).

## Running it

You just need Python 3.10 or newer.

Windows:
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run_pipeline.py
python scripts\run_analytics.py
```

Mac / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py
python scripts/run_analytics.py
```

It starts the mock payments API by itself, creates `data/retail.db`, and writes the report to
`reports/latest_exception_report.md`. You should see something like:

```
   source  ingested  valid  rejected  loaded
customers       202    192        10     192
 products        41     37         4      37
   orders      1507   1485        22    1485
 payments      1310   1301         9    1301

Validation errors logged:      45
Reconciliation exceptions:     62
```

There's a sample of the report in [docs/sample_exception_report.md](docs/sample_exception_report.md)
and of the analytics output in [docs/sample_analytics_output.md](docs/sample_analytics_output.md).

A few other things you can do:

```bash
python run_pipeline.py --regenerate               # rebuild the sample data first
python run_pipeline.py --settlement-window 0      # no grace period for late payments
python scripts/run_analytics.py top_customers     # run one query
python scripts/run_analytics.py --csv             # save results to reports/analytics/
python scripts/generate_sample_data.py --orders 10000 --seed 7
```

[DB Browser for SQLite](https://sqlitebrowser.org/) is handy for poking around the tables.

### Postgres

Same code, same SQL, just a different connection string. Install Postgres, create a database
called `retail`, then:

```bash
pip install -r requirements-postgres.txt
cp .env.example .env     # Windows: copy .env.example .env
```

and set `DATABASE_URL=postgresql+psycopg2://postgres:your_password@localhost:5432/retail` in `.env`.

### Pulling payments from Paystack

I wanted to try this against a real payment API rather than only my mock. Stripe isn't directly
available in South Africa, so I used [Paystack](https://paystack.com), which is part of Stripe and
has a free test mode. The connector only accepts test keys (`sk_test_...`) and refuses live ones.

1. Make a free account at dashboard.paystack.com and copy the **test** secret key into `.env` as
   `PAYSTACK_SECRET_KEY`.
2. Run `python scripts/seed_paystack_demo.py`. The first time it gives you a checkout link. Pay
   once with one of Paystack's [test cards](https://paystack.com/docs/payments/test-payments/),
   then run it again. It sends about 120 demo payments (with duplicates, wrong amounts and orphans
   mixed in) through `charge_authorization`. It's safe to re-run, nothing gets created twice.
3. Add the lines it prints to `.env` and run `python run_pipeline.py`.

Anything else already on the test account (like that first checkout payment) gets pulled in too
and shows up in the report, which is what would happen with a real business.

## What counts as an exception

| Exception | Severity | Meaning |
|---|---|---|
| `MISSING_PAYMENT` | high | Completed/shipped order with no successful payment, older than the settlement window |
| `AMOUNT_MISMATCH` | high | Paid amount is different from the order amount |
| `DUPLICATE_PAYMENT` | high | Charged more than once for the same order |
| `ORPHAN_PAYMENT` | high | Payment for an order id that doesn't exist anywhere |
| `PAYMENT_ON_CANCELLED_ORDER` | medium | Cancelled, but the card was still charged |
| `PAYMENT_FOR_REJECTED_ORDER` | medium | The order exists but failed validation |
| `PRICE_MISMATCH` | low | Sold at a different price than the catalog |

Two things are deliberately not flagged. A failed payment followed by a successful retry is just
normal customer behaviour. And payments often land a day or two after the order, so an unpaid order
is tagged `AWAITING_SETTLEMENT` until it's older than `SETTLEMENT_WINDOW_DAYS` (default 2). The
sample data has 5 of those at the end of the extract.

`fact_payments` has no foreign key to `fact_orders` on purpose. A payment for an order that doesn't
exist is exactly the kind of thing you want to keep and look at, not have the database reject.

## Tests

```bash
pytest
```

65 tests. The main end-to-end one generates data with a different seed from the committed sample,
runs the whole pipeline twice and checks that:

- the rejected record counts match what the generator planted (`defect_manifest.json`)
- each reconciliation exception type is found exactly as many times as it was planted
- ingested = valid + rejected, and valid = loaded, for every source
- the second run leaves the database the same
- all the analytics queries run

The Paystack connector is tested against a fake server that returns the response format from
Paystack's docs, and there's an end-to-end run in Paystack mode that has to find the same planted
problems. GitHub Actions runs everything on SQLite and on a real Postgres on every push.

## Layout

```
run_pipeline.py              entry point
pipeline/                    one module per step, plus config, db and the Paystack connector
mock_api/payment_api.py      the fake payments API (stdlib only)
scripts/                     data generator, analytics runner, Paystack seeding
sql/schema.sql               tables (same SQL for SQLite and Postgres)
sql/analytics/               the analysis queries
data/raw/                    sample CSVs + defect_manifest.json
tests/
docs/                        write-up, sample report, sample analytics output
```

## Things I learned along the way

- **Read everything as text first.** If you let pandas guess types, bad values quietly turn into
  NaN and you lose them. Reading as text means the error table shows exactly what the source sent.
- **Validation order matters.** Orders have to be checked against the customers and products that
  *passed*, not just the ones that exist in the file, otherwise the load fails on foreign keys.
- **Totals can lie.** In the sample run, expected revenue and collected payments are only $54
  apart. But underneath that there's about $6,000 of unpaid orders and $4,500 of double charges
  cancelling each other out. That's the whole reason to reconcile record by record.
- **False alarms matter as much as misses.** Before I added the settlement window, every order from
  the last couple of days showed up as a missing payment. A report like that gets ignored quickly.
- **Make the load re-runnable.** Doing the load in one transaction with a full refresh means running
  it twice (or after a crash) never duplicates anything.

## Limitations / what I'd do next

- It does a full refresh each run. With real volumes it should load incrementally with upserts.
- Refunds are ignored rather than netted off against the original payment.
- Only the Paystack transactions are reconciled, not the payouts to the bank or the fees.
- One currency per run.
- No scheduler. It would need cron / Task Scheduler / Airflow to run nightly.
- It would be good to fail the run (or alert) if the rejection rate suddenly jumps.
