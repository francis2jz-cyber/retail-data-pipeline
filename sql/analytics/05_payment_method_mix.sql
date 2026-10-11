-- Settled payments by method, with failure rate per method
SELECT
    payment_method,
    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END)                  AS successful_payments,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)                   AS failed_payments,
    ROUND(SUM(CASE WHEN status = 'success' THEN amount ELSE 0 END), 2)   AS settled_amount,
    ROUND(100.0 * SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) / COUNT(*), 1) AS failure_rate_pct
FROM fact_payments
GROUP BY payment_method
ORDER BY settled_amount DESC;
