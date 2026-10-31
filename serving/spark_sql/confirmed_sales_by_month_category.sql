-- Ventas confirmadas por mes comercial de Lima y categoría.
-- Los pedidos distintos se cuentan dentro de cada grupo.
SELECT
    d.year,
    d.month_number,
    p.category_id,
    p.category_name,
    COUNT(*) AS sales_lines,
    COUNT(DISTINCT f.order_id) AS confirmed_orders,
    SUM(f.quantity) AS units_sold,
    SUM(f.gross_amount_pen) AS gross_sales_pen,
    SUM(f.discount_amount_pen) AS discounts_pen,
    SUM(f.net_amount_pen) AS net_sales_pen
FROM fact_sales AS f
JOIN dim_date AS d
    ON f.date_key = d.date_key
JOIN dim_product AS p
    ON f.product_key = p.product_key
JOIN dim_order_status AS s
    ON f.order_status_key = s.order_status_key
WHERE s.counts_as_sale = true
GROUP BY
    d.year,
    d.month_number,
    p.category_id,
    p.category_name
ORDER BY
    d.year,
    d.month_number,
    p.category_id;
