-- Top 10 customers by lifetime value
WITH customer_value AS (
    SELECT
        o.customer_id,
        COUNT(*)            AS orders,
        SUM(o.order_amount) AS lifetime_value,
        MIN(o.order_date)   AS first_order,
        MAX(o.order_date)   AS last_order
    FROM fact_orders o
    WHERE o.status IN ('completed', 'shipped')
    GROUP BY o.customer_id
)
SELECT
    RANK() OVER (ORDER BY cv.lifetime_value DESC) AS value_rank,
    c.customer_id,
    c.full_name,
    c.country,
    cv.orders,
    ROUND(cv.lifetime_value, 2)                   AS lifetime_value,
    ROUND(cv.lifetime_value / cv.orders, 2)       AS avg_order_value,
    cv.first_order,
    cv.last_order
FROM customer_value cv
JOIN dim_customers c ON c.customer_id = cv.customer_id
ORDER BY value_rank
LIMIT 10;
