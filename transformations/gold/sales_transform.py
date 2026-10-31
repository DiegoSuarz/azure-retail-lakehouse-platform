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


def resolve_sales_dimension_keys(
    sales,
    dim_product,
    dim_customer,
    dim_date,
    dim_order_status,
):
    """Resuelve las cuatro claves dimensionales de cada línea de pedido."""
    lookups = (
        ("producto", dim_product, "product_id", "product_id", "product_key"),
        ("cliente", dim_customer, "customer_id", "customer_id", "customer_key"),
        ("fecha", dim_date, "business_date", "full_date", "date_key"),
        ("estado", dim_order_status, "status", "status", "order_status_key"),
    )

    result = sales

    for label, dimension, sales_column, dimension_column, key in lookups:
        if key in result.columns:
            raise ValueError(f"La venta ya contiene la clave: {key}")

        lookup = dimension.select(
            F.col(dimension_column).alias(sales_column),
            key,
        )

        invalid = (
            F.col(sales_column).isNull()
            | F.col(key).isNull()
            | (F.col(key) <= 0)
        )
        if lookup.filter(invalid).limit(1).count():
            raise ValueError(f"Referencia dimensional inválida: {label}")

        for column in (sales_column, key):
            if (
                lookup.groupBy(column)
                .count()
                .filter(F.col("count") > 1)
                .limit(1)
                .count()
            ):
                raise ValueError(
                    f"Referencia dimensional duplicada: {label}, {column}"
                )

        missing = result.join(
            lookup.select(sales_column),
            on=sales_column,
            how="left_anti",
        )
        if missing.limit(1).count():
            raise ValueError(f"Existen ventas sin dimensión de {label}.")

        result = result.join(
            lookup,
            on=sales_column,
            how="inner",
        )

    return result


def attach_sales_exchange_rate(sales, exchange_rates):
    """Añade la última tasa disponible con antigüedad máxima de siete días."""
    from pyspark.sql import types as T
    from pyspark.sql.window import Window

    output_columns = (
        "exchange_rate_series_code",
        "exchange_rate_date",
        "rate_pen_per_usd",
        "conversion_available",
    )
    if any(column in sales.columns for column in output_columns):
        raise ValueError("Las ventas ya contienen columnas cambiarias.")

    if not isinstance(sales.schema["business_date"].dataType, T.DateType):
        raise ValueError("business_date debe ser de tipo date.")

    if sales.filter(
        F.col("business_date").isNull()
    ).limit(1).count():
        raise ValueError("Existe una venta sin fecha comercial.")

    expected_types = (
        ("series_code", T.StringType()),
        ("observation_date", T.DateType()),
        ("rate_pen_per_usd", T.DecimalType(20, 14)),
        ("available", T.BooleanType()),
    )
    for column, expected_type in expected_types:
        if exchange_rates.schema[column].dataType != expected_type:
            raise ValueError(f"Tipo incompatible en tasas: {column}")

    rates = exchange_rates.select(
        "series_code",
        "observation_date",
        "rate_pen_per_usd",
        "available",
    )

    valid_rate = (
        (
            F.col("available")
            & F.col("rate_pen_per_usd").isNotNull()
            & (F.col("rate_pen_per_usd") > 0)
        )
        | (
            ~F.col("available")
            & F.col("rate_pen_per_usd").isNull()
        )
    )
    valid = (
        (F.col("series_code") == "PD04638PD")
        & F.col("observation_date").isNotNull()
        & F.col("available").isNotNull()
        & valid_rate
    )
    if rates.filter(
        ~F.coalesce(valid, F.lit(False))
    ).limit(1).count():
        raise ValueError("Observaciones cambiarias incompatibles.")

    if (
        rates.groupBy("series_code", "observation_date")
        .count()
        .filter(F.col("count") > 1)
        .limit(1)
        .count()
    ):
        raise ValueError("Observación cambiaria duplicada por serie y fecha.")

    business_dates = sales.select("business_date").distinct()
    available_rates = rates.filter(F.col("available"))

    candidates = business_dates.join(
        available_rates,
        on=(
            (F.col("observation_date") <= F.col("business_date"))
            & (
                F.datediff(
                    F.col("business_date"),
                    F.col("observation_date"),
                ) <= 7
            )
        ),
        how="left",
    )

    latest_first = (
        Window.partitionBy("business_date")
        .orderBy(F.col("observation_date").desc_nulls_last())
    )

    selected = (
        candidates
        .withColumn("_rate_rank", F.row_number().over(latest_first))
        .filter(F.col("_rate_rank") == 1)
        .select(
            "business_date",
            F.col("series_code").alias("exchange_rate_series_code"),
            F.col("observation_date").alias("exchange_rate_date"),
            "rate_pen_per_usd",
            F.col("rate_pen_per_usd")
            .isNotNull()
            .alias("conversion_available"),
        )
    )

    return sales.join(selected, on="business_date", how="left")


def calculate_sales_usd(sales):
    """Calcula importes USD con HALF_UP y neto por diferencia."""
    from decimal import Decimal, ROUND_HALF_UP, localcontext

    from pyspark.sql import types as T

    output_columns = (
        "gross_amount_usd",
        "discount_amount_usd",
        "net_amount_usd",
    )
    if any(column in sales.columns for column in output_columns):
        raise ValueError("Las ventas ya contienen importes USD.")

    expected_types = (
        ("gross_amount_pen", T.DecimalType(28, 2)),
        ("discount_amount_pen", T.DecimalType(28, 2)),
        ("net_amount_pen", T.DecimalType(28, 2)),
        ("rate_pen_per_usd", T.DecimalType(20, 14)),
        ("conversion_available", T.BooleanType()),
    )
    for column, expected_type in expected_types:
        if sales.schema[column].dataType != expected_type:
            raise ValueError(f"Tipo incompatible para conversión: {column}")

    valid_amounts = (
        (F.col("gross_amount_pen") >= 0)
        & (F.col("discount_amount_pen") >= 0)
        & (F.col("net_amount_pen") >= 0)
        & (
            F.col("net_amount_pen")
            == F.col("gross_amount_pen") - F.col("discount_amount_pen")
        )
    )
    valid_conversion = (
        (
            F.col("conversion_available")
            & F.col("rate_pen_per_usd").isNotNull()
            & (F.col("rate_pen_per_usd") > 0)
        )
        | (
            ~F.col("conversion_available")
            & F.col("rate_pen_per_usd").isNull()
        )
    )
    valid = (
        valid_amounts
        & F.col("conversion_available").isNotNull()
        & valid_conversion
    )
    if sales.filter(
        ~F.coalesce(valid, F.lit(False))
    ).limit(1).count():
        raise ValueError("Importes PEN o disponibilidad cambiaria incompatibles.")

    usd_schema = T.StructType([
        T.StructField(column, T.DecimalType(28, 2), nullable=True)
        for column in output_columns
    ])

    def convert_amounts(gross, discount, rate, available):
        if not available:
            return None, None, None

        with localcontext() as context:
            context.prec = 80
            cent = Decimal("0.01")
            gross_usd = (gross / rate).quantize(
                cent, rounding=ROUND_HALF_UP
            )
            discount_usd = (discount / rate).quantize(
                cent, rounding=ROUND_HALF_UP
            )
            net_usd = gross_usd - discount_usd

            amounts = (gross_usd, discount_usd, net_usd)
            if any(abs(value) >= Decimal("1e26") for value in amounts):
                raise ValueError("Importe USD fuera de decimal(28,2).")

            return amounts

    convert = F.udf(convert_amounts, usd_schema)

    converted = sales.withColumn(
        "_usd_amounts",
        convert(
            F.col("gross_amount_pen"),
            F.col("discount_amount_pen"),
            F.col("rate_pen_per_usd"),
            F.col("conversion_available"),
        ),
    )

    return converted.select(
        *[F.col(column) for column in sales.columns],
        *[
            F.col(f"_usd_amounts.{column}").alias(column)
            for column in output_columns
        ],
    )


def build_sales_fact(
    order_items,
    orders,
    dim_product,
    dim_customer,
    dim_date,
    dim_order_status,
    exchange_rates,
    gold_processing_run_id,
    gold_processed_at,
):
    """Construye los hechos de ventas con claves, importes y procedencia."""
    from datetime import datetime, timezone

    if (
        not isinstance(gold_processing_run_id, str)
        or not gold_processing_run_id.strip()
    ):
        raise ValueError("Se requiere gold_processing_run_id no vacío.")

    if (
        not isinstance(gold_processed_at, datetime)
        or gold_processed_at.tzinfo is None
        or gold_processed_at.utcoffset() is None
    ):
        raise ValueError("gold_processed_at debe incluir zona horaria.")

    processed_at_utc = gold_processed_at.astimezone(timezone.utc)

    amounts = prepare_sales_amounts(order_items)
    contextualized = attach_order_context(amounts, orders)

    dimensional = resolve_sales_dimension_keys(
        contextualized,
        dim_product,
        dim_customer,
        dim_date,
        dim_order_status,
    )

    rated = attach_sales_exchange_rate(dimensional, exchange_rates)
    converted = calculate_sales_usd(rated)

    return (
        converted
        .select(
            "order_id",
            "line_number",
            "product_key",
            "customer_key",
            "date_key",
            "order_status_key",
            "order_date_utc",
            "currency_code",
            "quantity",
            "unit_price_pen",
            "gross_amount_pen",
            "discount_amount_pen",
            "net_amount_pen",
            "exchange_rate_series_code",
            "exchange_rate_date",
            "rate_pen_per_usd",
            "conversion_available",
            "gross_amount_usd",
            "discount_amount_usd",
            "net_amount_usd",
        )
        .withColumn(
            "gold_processing_run_id",
            F.lit(gold_processing_run_id),
        )
        .withColumn(
            "gold_processed_at",
            F.lit(processed_at_utc),
        )
    )
