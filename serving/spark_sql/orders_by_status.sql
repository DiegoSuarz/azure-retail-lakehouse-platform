-- Distribución operativa de pedidos por estado.
-- Los importes pending y cancelled no representan ventas confirmadas.
SELECT
    s.order_status_key,
    s.status,
    s.status_name,
    s.counts_as_sale,
    COUNT(f.order_id) AS order_lines,
    COUNT(DISTINCT f.order_id) AS orders,
    SUM(f.quantity) AS units,
    SUM(f.net_amount_pen) AS net_amount_pen
FROM dim_order_status AS s
LEFT JOIN fact_sales AS f
    ON s.order_status_key = f.order_status_key
GROUP BY
    s.order_status_key,
    s.status,
    s.status_name,
    s.counts_as_sale
ORDER BY
    s.order_status_key;
