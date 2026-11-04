"""Preparación de correcciones SCD tipo 1 sobre todas las versiones."""

from datetime import datetime, timezone
from functools import reduce
from operator import or_

from pyspark.sql import functions as F
from pyspark.sql import types as T

from transformations.gold.scd_changes import detect_scd_changes
from transformations.gold.scd_rules import SCD_RULES


def prepare_type1_updates(
    incoming, dimension, dimension_name, batch_id, run_id, processed_at
):
    """Devuelve la dimensión corregida, sin realizar escrituras."""
    for name, value in (("batch_id", batch_id), ("run_id", run_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Se requiere {name} no vacío.")

    if (
        not isinstance(processed_at, datetime)
        or processed_at.tzinfo is None
        or processed_at.utcoffset() is None
    ):
        raise ValueError("processed_at debe incluir zona horaria.")
    processed_at = processed_at.astimezone(timezone.utc)

    if dimension.sparkSession.conf.get("spark.sql.session.timeZone") != "UTC":
        raise ValueError("La sesión Spark debe utilizar UTC.")

    audit_types = {
        "scd_last_modified_batch_id": T.StringType(),
        "scd_last_modified_run_id": T.StringType(),
        "scd_last_modified_at": T.TimestampType(),
    }
    for name, expected in audit_types.items():
        if name not in dimension.columns or dimension.schema[name].dataType != expected:
            raise ValueError(f"Columna de auditoría ausente o incompatible: {name}")

    changes = detect_scd_changes(incoming, dimension, dimension_name)
    rules = SCD_RULES[dimension_name]
    business_key = rules["business_key"]
    attributes = rules["type1"]

    corrections = changes.filter(
        F.col("has_type1_change")
    ).select(business_key, *attributes)

    joined = dimension.alias("stored").join(
        corrections.alias("correction"),
        F.col(f"stored.{business_key}") == F.col(f"correction.{business_key}"),
        "left",
    )

    differences = [
        ~F.col(f"stored.{name}").eqNullSafe(F.col(f"correction.{name}"))
        for name in attributes
    ]
    needs_update = (
        F.col(f"correction.{business_key}").isNotNull()
        & reduce(or_, differences, F.lit(False))
    )

    invalid_time = (
        F.col("stored.scd_last_modified_at").isNull()
        | (F.col("stored.scd_last_modified_at") > F.lit(processed_at))
    )
    if joined.filter(needs_update & invalid_time).limit(1).count():
        raise ValueError("Auditoría temporal inválida en una fila por corregir.")

    replacements = {
        name: F.col(f"correction.{name}")
        for name in attributes
    }
    replacements.update({
        "scd_last_modified_batch_id": F.lit(batch_id),
        "scd_last_modified_run_id": F.lit(run_id),
        "scd_last_modified_at": F.lit(processed_at),
    })

    return joined.select(*[
        (
            F.when(needs_update, replacements[name])
            .otherwise(F.col(f"stored.{name}"))
            .alias(name)
        )
        if name in replacements
        else F.col(f"stored.{name}")
        for name in dimension.columns
    ])
