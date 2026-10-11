-- Revenue, customers and orders per customer by country
SELECT
    c.country,
    COUNT(DISTINCT c.customer_id)                                   AS customers,
    COUNT(o.order_id)                                               AS orders,
    ROUND(SUM(o.order_amount), 2)                                   AS revenue,
    ROUND(1.0 * COUNT(o.order_id) / COUNT(DISTINCT c.customer_id), 1) AS orders_per_customer
FROM dim_customers c
JOIN fact_orders o ON o.customer_id = c.customer_id
WHERE o.status IN ('completed', 'shipped')
GROUP BY c.country
ORDER BY revenue DESC;
