-- Validation errors in the latest batch, by source and rule
SELECT
    source,
    rule,
    column_name,
    COUNT(*)                   AS errors,
    COUNT(DISTINCT record_key) AS distinct_records
FROM err_validation_errors
WHERE batch_id = (SELECT MAX(batch_id) FROM err_validation_errors)
GROUP BY source, rule, column_name
ORDER BY source, errors DESC;
