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


def validate_legacy_sales(
    sales, accepted_sales, accepted_dimensions, dimensions
):
    """Verifica ventas M9 intactas y sus referencias, sin exigir vigencias."""
    for label, frame in (("ventas", sales), ("base M9", accepted_sales)):
        if len(frame.columns) != len(set(frame.columns)):
            raise ValueError(f"Columnas duplicadas en {label}.")

    expected_schema = [
        (field.name, field.dataType) for field in accepted_sales.schema
    ]
    actual_schema = [
        (field.name, field.dataType) for field in sales.schema
    ]
    if actual_schema != expected_schema:
        raise ValueError("El esquema de ventas difiere de la base M9.")

    required = {
        "order_id": T.IntegerType(),
        "line_number": T.IntegerType(),
        "product_key": T.LongType(),
        "customer_key": T.LongType(),
    }
    for name, expected in required.items():
        if name not in sales.columns or sales.schema[name].dataType != expected:
            raise ValueError(f"Columna de ventas ausente o incompatible: {name}")

    invalid_keys = [
        F.col(name).isNull() | (F.col(name) <= 0)
        for name in required
    ]
    if sales.filter(reduce(or_, invalid_keys)).limit(1).count():
        raise ValueError("Las ventas heredadas contienen claves inválidas.")

    grain = ("order_id", "line_number")
    if sales.groupBy(*grain).count().filter("count > 1").limit(1).count():
        raise ValueError("Las ventas heredadas contienen líneas duplicadas.")

    if (
        sales.exceptAll(accepted_sales).limit(1).count()
        or accepted_sales.exceptAll(sales).limit(1).count()
    ):
        raise ValueError("Los datos de ventas difieren de la base M9.")

    relationships = {}
    for name in ("dim_product", "dim_customer"):
        rules = SCD_RULES[name]
        version_key = rules["version_key"]
        business_key = rules["business_key"]

        if name not in accepted_dimensions or name not in dimensions:
            raise ValueError(f"Falta una dimensión para validar: {name}")

        baseline = accepted_dimensions[name]
        dimension = dimensions[name]
        for label, frame in (("base M9", baseline), ("SCD", dimension)):
            if len(frame.columns) != len(set(frame.columns)):
                raise ValueError(f"Columnas duplicadas en {name}, {label}.")
            for column, expected in (
                (version_key, T.LongType()),
                (business_key, T.IntegerType()),
            ):
                if column not in frame.columns or frame.schema[column].dataType != expected:
                    raise ValueError(f"Clave incompatible en {name}, {label}: {column}")

        referenced = sales.select(version_key).distinct()
        for label, frame in (("base M9", baseline), ("SCD", dimension)):
            matches = referenced.join(
                frame.select(version_key, business_key),
                version_key,
                "left",
            )
            counts = matches.groupBy(version_key).agg(
                F.count(F.lit(1)).alias("result_rows"),
                F.count(business_key).alias("matched_entities"),
            )
            if counts.filter(
                (F.col("result_rows") != 1)
                | (F.col("matched_entities") != 1)
            ).limit(1).count():
                raise ValueError(f"Referencia ausente, duplicada o nula: {name}, {label}")

        expected_mapping = referenced.join(
            baseline.select(version_key, business_key),
            version_key,
            "inner",
        )
        if expected_mapping.join(
            dimension.select(version_key, business_key),
            [version_key, business_key],
            "left_anti",
        ).limit(1).count():
            raise ValueError(f"Una clave heredada identifica otra entidad: {name}")

        relationships[name] = {
            "references_verified": True,
            "entity_mapping_preserved": True,
        }

    return {
        "passed": True,
        "row_count": sales.count(),
        "sales_unchanged": True,
        "relationships": relationships,
    }
