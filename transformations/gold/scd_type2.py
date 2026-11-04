"""Preparación de nuevas versiones SCD tipo 2."""

from pyspark.sql import functions as F
from pyspark.sql.window import Window

from transformations.gold.scd_rules import SCD_RULES


def assign_new_version_keys(changes, dimension, dimension_name):
    """Asigna claves usando cambios validados y la misma base dimensional."""
    if dimension_name not in SCD_RULES:
        raise ValueError("Dimensión no admitida para asignar claves SCD.")

    rules = SCD_RULES[dimension_name]
    business_key = rules["business_key"]
    version_key = rules["version_key"]

    candidates = changes.filter(
        F.col("change_type").isin("new", "type2", "type1_and_type2")
    ).select(
        business_key,
        "existing_version_key",
        "change_type",
    )

    maximum = dimension.agg(
        F.max(version_key).alias("maximum")
    ).first()["maximum"]
    maximum = 0 if maximum is None else maximum

    candidate_count = candidates.count()
    if maximum + candidate_count > 9223372036854775807:
        raise ValueError("Las nuevas claves exceden el rango de long.")

    position = F.row_number().over(
        Window.orderBy(business_key)
    ).cast("long")

    return candidates.withColumn(
        "new_version_key",
        F.lit(maximum).cast("long") + position,
    )
