-- =====================================================================
-- Retail Data Pipeline schema
-- Portable SQL: runs unchanged on SQLite and PostgreSQL.
-- Layers are separated by table prefix:
--   stg_    raw landing zone (everything stored as text, as received)
--   err_    records rejected by validation
--   dim_ / fact_   clean, typed, analytics-ready model
--   recon_  reconciliation exceptions
--   audit_  pipeline run log
-- =====================================================================

-- ---------- STAGING (raw, untyped) ----------
CREATE TABLE IF NOT EXISTS stg_customers (
    customer_id   TEXT,
    first_name    TEXT,
    last_name     TEXT,
    email         TEXT,
    country       TEXT,
    signup_date   TEXT,
    _batch_id     TEXT,
    _source       TEXT,
    _ingested_at  TEXT
);

CREATE TABLE IF NOT EXISTS stg_products (
    product_id     TEXT,
    product_name   TEXT,
    category       TEXT,
    unit_price     TEXT,
    stock_quantity TEXT,
    last_updated   TEXT,
    _batch_id      TEXT,
    _source        TEXT,
    _ingested_at   TEXT
);

CREATE TABLE IF NOT EXISTS stg_orders (
    order_id     TEXT,
    customer_id  TEXT,
    product_id   TEXT,
    quantity     TEXT,
    unit_price   TEXT,
    order_date   TEXT,
    status       TEXT,
    _batch_id    TEXT,
    _source      TEXT,
    _ingested_at TEXT
);

CREATE TABLE IF NOT EXISTS stg_payments (
    payment_id     TEXT,
    order_id       TEXT,
    amount         TEXT,
    currency       TEXT,
    payment_method TEXT,
    status         TEXT,
    paid_at        TEXT,
    _batch_id      TEXT,
    _source        TEXT,
    _ingested_at   TEXT
);

-- ---------- ERROR TABLE ----------
CREATE TABLE IF NOT EXISTS err_validation_errors (
    batch_id      TEXT NOT NULL,
    source        TEXT NOT NULL,
    record_key    TEXT,
    rule          TEXT NOT NULL,
    column_name   TEXT,
    invalid_value TEXT,
    error_message TEXT,
    raw_record    TEXT,
    logged_at     TEXT
);

-- ---------- CORE MODEL ----------
CREATE TABLE IF NOT EXISTS dim_customers (
    customer_id  TEXT PRIMARY KEY,
    first_name   TEXT NOT NULL,
    last_name    TEXT NOT NULL,
    full_name    TEXT NOT NULL,
    email        TEXT NOT NULL,
    country      TEXT NOT NULL,
    signup_date  DATE NOT NULL,
    _batch_id    TEXT
);

CREATE TABLE IF NOT EXISTS dim_products (
    product_id     TEXT PRIMARY KEY,
    product_name   TEXT NOT NULL,
    category       TEXT NOT NULL,
    list_price     NUMERIC(12, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    last_updated   DATE,
    _batch_id      TEXT
);

CREATE TABLE IF NOT EXISTS fact_orders (
    order_id              TEXT PRIMARY KEY,
    customer_id           TEXT NOT NULL REFERENCES dim_customers (customer_id),
    product_id            TEXT NOT NULL REFERENCES dim_products (product_id),
    quantity              INTEGER NOT NULL,
    unit_price            NUMERIC(12, 2) NOT NULL,
    order_amount          NUMERIC(12, 2) NOT NULL,
    order_date            DATE NOT NULL,
    order_month           TEXT NOT NULL,
    status                TEXT NOT NULL,
    reconciliation_status TEXT,
    _batch_id             TEXT
);

-- No foreign key to fact_orders on purpose: orphan payments are kept and flagged.
CREATE TABLE IF NOT EXISTS fact_payments (
    payment_id            TEXT PRIMARY KEY,
    order_id              TEXT NOT NULL,
    amount                NUMERIC(12, 2) NOT NULL,
    currency              TEXT NOT NULL,
    payment_method        TEXT NOT NULL,
    status                TEXT NOT NULL,
    paid_at               TIMESTAMP NOT NULL,
    paid_date             DATE NOT NULL,
    reconciliation_status TEXT,
    _batch_id             TEXT
);

-- ---------- RECONCILIATION ----------
CREATE TABLE IF NOT EXISTS recon_exceptions (
    batch_id        TEXT NOT NULL,
    exception_type  TEXT NOT NULL,
    severity        TEXT NOT NULL,
    order_id        TEXT,
    payment_id      TEXT,
    expected_amount NUMERIC(12, 2),
    actual_amount   NUMERIC(12, 2),
    difference      NUMERIC(12, 2),
    details         TEXT,
    logged_at       TEXT
);

-- ---------- AUDIT ----------
CREATE TABLE IF NOT EXISTS audit_pipeline_runs (
    batch_id         TEXT PRIMARY KEY,
    started_at       TEXT NOT NULL,
    finished_at      TEXT,
    status           TEXT NOT NULL,
    database_backend TEXT,
    rows_ingested    INTEGER,
    rows_valid       INTEGER,
    rows_rejected    INTEGER,
    recon_exceptions INTEGER,
    error_message    TEXT
);

CREATE INDEX IF NOT EXISTS ix_fact_orders_customer ON fact_orders (customer_id);
CREATE INDEX IF NOT EXISTS ix_fact_orders_month ON fact_orders (order_month);
CREATE INDEX IF NOT EXISTS ix_fact_payments_order ON fact_payments (order_id);
CREATE INDEX IF NOT EXISTS ix_err_batch ON err_validation_errors (batch_id);
CREATE INDEX IF NOT EXISTS ix_recon_batch ON recon_exceptions (batch_id);
