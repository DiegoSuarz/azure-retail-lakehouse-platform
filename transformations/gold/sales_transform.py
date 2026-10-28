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


def attach_order_context(amounts, orders):
    """Incorpora el contexto del pedido sin perder ni multiplicar líneas."""
    from transformations.gold.dimensions import add_order_business_date

    for frame, keys in (
        (orders, ["order_id"]),
        (amounts, ["order_id", "line_number"]),
    ):
        invalid_key = F.lit(False)
        for key in keys:
            invalid_key = invalid_key | F.col(key).isNull() | (F.col(key) <= 0)

        if frame.filter(invalid_key).limit(1).count():
            raise ValueError(f"Clave nula o no positiva: {keys}")

        if (
            frame.groupBy(*keys)
            .count()
            .filter(F.col("count") > 1)
            .limit(1)
            .count()
        ):
            raise ValueError(f"Clave duplicada: {keys}")

    valid_order = (
        (F.col("customer_id") > 0)
        & (F.col("currency_code") == "PEN")
        & F.col("status").isin("pending", "confirmed", "cancelled")
    )
    if orders.filter(
        ~F.coalesce(valid_order, F.lit(False))
    ).limit(1).count():
        raise ValueError("Cliente, moneda o estado del pedido incompatible.")

    missing = amounts.join(
        orders.select("order_id"),
        on="order_id",
        how="left_anti",
    )
    if missing.limit(1).count():
        raise ValueError("Existen líneas sin pedido.")

    context = add_order_business_date(orders).select(
        "order_id",
        "customer_id",
        F.col("order_date").alias("order_date_utc"),
        "business_date",
        "currency_code",
        "status",
    )

    return amounts.join(context, on="order_id", how="inner")
