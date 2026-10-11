-- Revenue and share by product category
SELECT
    p.category,
    COUNT(DISTINCT o.product_id)                                       AS products_sold,
    SUM(o.quantity)                                                    AS units_sold,
    ROUND(SUM(o.order_amount), 2)                                      AS revenue,
    ROUND(100.0 * SUM(o.order_amount) / SUM(SUM(o.order_amount)) OVER (), 1) AS revenue_share_pct
FROM fact_orders o
JOIN dim_products p ON p.product_id = o.product_id
WHERE o.status IN ('completed', 'shipped')
GROUP BY p.category
ORDER BY revenue DESC;
