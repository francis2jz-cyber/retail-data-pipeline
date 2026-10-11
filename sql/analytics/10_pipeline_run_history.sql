-- Pipeline run history with rejection rate per run
SELECT
    batch_id,
    status,
    database_backend,
    started_at,
    finished_at,
    rows_ingested,
    rows_rejected,
    ROUND(100.0 * rows_rejected / rows_ingested, 2) AS rejection_rate_pct,
    recon_exceptions
FROM audit_pipeline_runs
ORDER BY batch_id DESC
LIMIT 10;
