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


def prepare_version_closures(
    dimension, plan, dimension_name,
    batch_id, run_id, observed_at, processed_at,
):
    """Prepara cierres tipo 2 usando un plan validado sobre la misma base."""
    from datetime import datetime, timezone
    from pyspark.sql import types as T

    if dimension_name not in SCD_RULES:
        raise ValueError("Dimensión no admitida para cerrar versiones.")

    for name, value in (("batch_id", batch_id), ("run_id", run_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Se requiere {name} no vacío.")

    instants = {}
    for name, value in (
        ("observed_at", observed_at),
        ("processed_at", processed_at),
    ):
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(f"{name} debe incluir zona horaria.")
        instants[name] = value.astimezone(timezone.utc)

    observed_at = instants["observed_at"]
    processed_at = instants["processed_at"]
    if processed_at < observed_at:
        raise ValueError("El procesamiento no puede preceder a la observación.")

    if dimension.sparkSession.conf.get("spark.sql.session.timeZone") != "UTC":
        raise ValueError("La sesión Spark debe utilizar UTC.")

    required_types = {
        "valid_from": T.TimestampType(),
        "valid_to": T.TimestampType(),
        "is_current": T.BooleanType(),
        "scd_last_modified_batch_id": T.StringType(),
        "scd_last_modified_run_id": T.StringType(),
        "scd_last_modified_at": T.TimestampType(),
    }
    for name, expected in required_types.items():
        if name not in dimension.columns or dimension.schema[name].dataType != expected:
            raise ValueError(f"Columna dimensional ausente o incompatible: {name}")

    rules = SCD_RULES[dimension_name]
    business_key = rules["business_key"]
    version_key = rules["version_key"]

    closures = plan.filter(
        F.col("change_type").isin("type2", "type1_and_type2")
    ).select(business_key, "existing_version_key")

    if closures.filter(
        F.col("existing_version_key").isNull()
    ).limit(1).count():
        raise ValueError("El plan contiene un cierre sin clave de versión.")

    if (
        closures.groupBy("existing_version_key").count()
        .filter("count > 1").limit(1).count()
    ):
        raise ValueError("El plan contiene cierres duplicados.")

    matched = closures.alias("closure").join(
        dimension.alias("stored"),
        (
            F.col("closure.existing_version_key")
            == F.col(f"stored.{version_key}")
        )
        & (
            F.col(f"closure.{business_key}")
            == F.col(f"stored.{business_key}")
        ),
        "left",
    )
    invalid = (
        F.col(f"stored.{version_key}").isNull()
        | ~F.col("stored.is_current").eqNullSafe(F.lit(True))
        | F.col("stored.valid_to").isNotNull()
        | F.col("stored.valid_from").isNull()
        | (F.col("stored.valid_from") >= F.lit(observed_at))
        | F.col("stored.scd_last_modified_at").isNull()
        | (F.col("stored.scd_last_modified_at") > F.lit(processed_at))
    )
    if matched.filter(invalid).limit(1).count():
        raise ValueError("Cierre incompatible con la versión actual o sus fechas.")

    joined = dimension.alias("stored").join(
        closures.select("existing_version_key").alias("closure"),
        F.col(f"stored.{version_key}") == F.col("closure.existing_version_key"),
        "left",
    )
    needs_closure = F.col("closure.existing_version_key").isNotNull()

    replacements = {
        "valid_to": F.lit(observed_at),
        "is_current": F.lit(False),
        "scd_last_modified_batch_id": F.lit(batch_id),
        "scd_last_modified_run_id": F.lit(run_id),
        "scd_last_modified_at": F.lit(processed_at),
    }
    return joined.select(*[
        (
            F.when(needs_closure, replacements[name])
            .otherwise(F.col(f"stored.{name}"))
            .alias(name)
        )
        if name in replacements
        else F.col(f"stored.{name}")
        for name in dimension.columns
    ])
