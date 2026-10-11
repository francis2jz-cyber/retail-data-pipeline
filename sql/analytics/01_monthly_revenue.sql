-- Monthly revenue trend with running total and month-over-month growth
WITH monthly AS (
    SELECT
        order_month,
        COUNT(*)          AS orders,
        SUM(quantity)     AS units_sold,
        SUM(order_amount) AS revenue
    FROM fact_orders
    WHERE status IN ('completed', 'shipped')
    GROUP BY order_month
)
SELECT
    order_month,
    orders,
    units_sold,
    ROUND(revenue, 2)                                        AS revenue,
    ROUND(revenue / orders, 2)                               AS avg_order_value,
    ROUND(SUM(revenue) OVER (ORDER BY order_month), 2)       AS running_revenue,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY order_month))
          / LAG(revenue) OVER (ORDER BY order_month), 1)     AS mom_growth_pct
FROM monthly
ORDER BY order_month;
