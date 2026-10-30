"""Construcción de tablas complementarias de Gold."""

from pyspark.sql import functions as F
from pyspark.sql import types as T


def build_exchange_rate_reference(exchange_rates):
    """Conserva las observaciones cambiarias válidas y no disponibles."""
    expected_types = (
        ("series_code", T.StringType()),
        ("observation_date", T.DateType()),
        ("rate_pen_per_usd", T.DecimalType(20, 14)),
        ("available", T.BooleanType()),
        ("raw_value", T.StringType()),
    )
    for column, expected_type in expected_types:
        if exchange_rates.schema[column].dataType != expected_type:
            raise ValueError(f"Tipo incompatible en referencia: {column}")

    reference = exchange_rates.select(
        *[column for column, _ in expected_types]
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
        & F.col("raw_value").isNotNull()
        & valid_rate
    )
    if reference.filter(
        ~F.coalesce(valid, F.lit(False))
    ).limit(1).count():
        raise ValueError("Referencia cambiaria incompatible.")

    if (
        reference.groupBy("series_code", "observation_date")
        .count()
        .filter(F.col("count") > 1)
        .limit(1)
        .count()
    ):
        raise ValueError("Referencia cambiaria duplicada por serie y fecha.")

    return reference
