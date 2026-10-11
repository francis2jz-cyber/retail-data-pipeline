-- Reconciliation exceptions in the latest batch, by type and severity
SELECT
    exception_type,
    severity,
    COUNT(*)                         AS exceptions,
    ROUND(SUM(ABS(difference)), 2)   AS total_abs_difference
FROM recon_exceptions
WHERE batch_id = (SELECT MAX(batch_id) FROM recon_exceptions)
GROUP BY exception_type, severity
ORDER BY
    CASE severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
    exceptions DESC;
