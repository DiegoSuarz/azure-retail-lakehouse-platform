"""Resolución temporal de claves dimensionales para ventas nuevas."""

from functools import reduce
from operator import or_

from pyspark.sql import functions as F
from pyspark.sql import types as T

from transformations.gold.scd_rules import SCD_RULES


def resolve_sales_scd_key(sales, dimension, dimension_name):
    """Añade una clave SCD por línea usando una dimensión validada."""
    if dimension_name not in SCD_RULES:
        raise ValueError("Dimensión no admitida para resolver claves de ventas.")

    rules = SCD_RULES[dimension_name]
    business_key = rules["business_key"]
    version_key = rules["version_key"]
    grain = ("order_id", "line_number")

    if sales.sparkSession.conf.get("spark.sql.session.timeZone") != "UTC":
        raise ValueError("La sesión Spark debe utilizar UTC.")

    for label, frame in (("ventas", sales), ("dimensión", dimension)):
        if len(frame.columns) != len(set(frame.columns)):
            raise ValueError(f"Columnas duplicadas en {label}.")

    if version_key in sales.columns:
        raise ValueError(f"La venta ya contiene la clave: {version_key}")

    sales_types = {
        "order_id": T.IntegerType(),
        "line_number": T.IntegerType(),
        business_key: T.IntegerType(),
        "order_date_utc": T.TimestampType(),
    }
    dimension_types = {
        business_key: T.IntegerType(),
        version_key: T.LongType(),
        "valid_from": T.TimestampType(),
        "valid_to": T.TimestampType(),
    }
    for label, frame, required in (
        ("ventas", sales, sales_types),
        ("dimensión", dimension, dimension_types),
    ):
        for name, expected in required.items():
            if name not in frame.columns or frame.schema[name].dataType != expected:
                raise ValueError(f"Columna ausente o incompatible en {label}: {name}")

    invalid_keys = [
        F.col(name).isNull() | (F.col(name) <= 0)
        for name in (*grain, business_key)
    ]
    invalid_sale = (
        reduce(or_, invalid_keys)
        | F.col("order_date_utc").isNull()
    )
    if sales.filter(invalid_sale).limit(1).count():
        raise ValueError("Venta con claves inválidas o fecha nula.")

    if sales.groupBy(*grain).count().filter("count > 1").limit(1).count():
        raise ValueError("El grano de ventas contiene líneas duplicadas.")

    sale_at = F.col("sale.order_date_utc")
    matches = (
        (F.col(f"sale.{business_key}") == F.col(f"version.{business_key}"))
        & (sale_at >= F.col("version.valid_from"))
        & (
            F.col("version.valid_to").isNull()
            | (sale_at < F.col("version.valid_to"))
        )
    )
    resolved = sales.alias("sale").join(
        dimension.alias("version"), matches, "left"
    ).select(
        "sale.*",
        F.col(f"version.{version_key}").alias(version_key),
    )

    match_counts = resolved.groupBy(*grain).agg(
        F.count(F.lit(1)).alias("result_rows"),
        F.count(version_key).alias("matched_versions"),
    )
    invalid_matches = (
        (F.col("result_rows") != 1)
        | (F.col("matched_versions") != 1)
    )
    if match_counts.filter(invalid_matches).limit(1).count():
        raise ValueError(
            f"Cada línea requiere exactamente una versión temporal: {dimension_name}"
        )

    return resolved
