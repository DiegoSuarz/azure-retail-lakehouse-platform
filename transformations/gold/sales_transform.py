"""Construcción de los hechos de ventas de Gold."""

from pyspark.sql import functions as F


def prepare_sales_amounts(order_items):
    """Calcula importes históricos en PEN por línea de pedido."""
    amounts = order_items.select(
        "order_id",
        "line_number",
        "product_id",
        "quantity",
        F.col("unit_price").alias("unit_price_pen"),
        F.col("discount_amount")
        .cast("decimal(28,2)")
        .alias("discount_amount_pen"),
    )

    amounts = (
        amounts
        .withColumn(
            "gross_amount_pen",
            (F.col("quantity") * F.col("unit_price_pen"))
            .cast("decimal(28,2)"),
        )
        .withColumn(
            "net_amount_pen",
            (F.col("gross_amount_pen") - F.col("discount_amount_pen"))
            .cast("decimal(28,2)"),
        )
    )

    valid = (
        (F.col("quantity") > 0)
        & (F.col("unit_price_pen") > 0)
        & (F.col("discount_amount_pen") >= 0)
        & (F.col("net_amount_pen") >= 0)
        & F.col("gross_amount_pen").isNotNull()
    )

    if amounts.filter(
        ~F.coalesce(valid, F.lit(False))
    ).limit(1).count():
        raise ValueError("Importes de línea nulos, negativos o incompatibles.")

    return amounts
