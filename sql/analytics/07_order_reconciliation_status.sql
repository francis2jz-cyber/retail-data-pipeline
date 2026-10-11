-- How many orders reconcile cleanly, and how much money sits in each status
SELECT
    reconciliation_status,
    COUNT(*)                                            AS orders,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)  AS pct_of_orders,
    ROUND(SUM(order_amount), 2)                         AS order_value
FROM fact_orders
GROUP BY reconciliation_status
ORDER BY orders DESC;
