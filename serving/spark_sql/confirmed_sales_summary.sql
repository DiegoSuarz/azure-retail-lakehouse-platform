-- Resumen de ventas confirmadas.
-- El total USD incluye únicamente líneas con conversión disponible.
SELECT
    COUNT(*) AS sales_lines,
    COUNT(DISTINCT f.order_id) AS confirmed_orders,
    SUM(f.quantity) AS units_sold,
    SUM(f.net_amount_pen) AS net_sales_pen,
    CAST(
        ROUND(
            SUM(f.net_amount_pen)
            / NULLIF(COUNT(DISTINCT f.order_id), 0),
            2
        ) AS DECIMAL(28,2)
    ) AS average_order_value_pen,
    COUNT(
        CASE WHEN f.conversion_available THEN 1 END
    ) AS converted_lines,
    COUNT(
        CASE WHEN NOT f.conversion_available THEN 1 END
    ) AS unconverted_lines,
    SUM(
        CASE
            WHEN NOT f.conversion_available
            THEN f.net_amount_pen
            ELSE CAST(0 AS DECIMAL(28,2))
        END
    ) AS unconverted_net_pen,
    SUM(
        CASE
            WHEN f.conversion_available
            THEN f.net_amount_usd
        END
    ) AS converted_net_sales_usd
FROM fact_sales AS f
JOIN dim_order_status AS s
    ON f.order_status_key = s.order_status_key
WHERE s.counts_as_sale = true;
