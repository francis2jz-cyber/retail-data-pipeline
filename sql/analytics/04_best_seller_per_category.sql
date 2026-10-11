-- Best-selling product in each category (window function ranking)
WITH product_sales AS (
    SELECT
        p.category,
        p.product_name,
        SUM(o.quantity)     AS units_sold,
        SUM(o.order_amount) AS revenue,
        ROW_NUMBER() OVER (PARTITION BY p.category ORDER BY SUM(o.order_amount) DESC) AS rn
    FROM fact_orders o
    JOIN dim_products p ON p.product_id = o.product_id
    WHERE o.status IN ('completed', 'shipped')
    GROUP BY p.category, p.product_name
)
SELECT category, product_name, units_sold, ROUND(revenue, 2) AS revenue
FROM product_sales
WHERE rn = 1
ORDER BY revenue DESC;
