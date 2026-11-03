"""Preparación de dimensiones iniciales SCD desde Gold aceptado."""

from datetime import datetime, timezone

from pyspark.sql import functions as F
from pyspark.sql import types as T


SCD_COLUMNS = (
    "valid_from",
    "valid_to",
    "is_current",
    "scd_created_batch_id",
    "scd_last_modified_batch_id",
    "scd_last_modified_run_id",
    "scd_last_modified_at",
)


def initialize_scd_dimension(
    frame, dimension, batch_id, run_id, observed_at, processed_at
):
    """Añade estructura SCD preservando claves, atributos y procedencia."""
    keys = {
        "dim_product": ("product_key", "product_id"),
        "dim_customer": ("customer_key", "customer_id"),
    }
    if dimension not in keys:
        raise ValueError("Dimensión no admitida para inicialización SCD.")

    if frame.sparkSession.conf.get("spark.sql.session.timeZone") != "UTC":
        raise ValueError("La sesión Spark debe utilizar UTC.")

    if len(frame.columns) != len(set(frame.columns)):
        raise ValueError("La entrada contiene nombres de columna duplicados.")

    if set(SCD_COLUMNS).intersection(frame.columns):
        raise ValueError("La entrada ya contiene columnas SCD.")

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

    if instants["processed_at"] < instants["observed_at"]:
        raise ValueError("El procesamiento no puede preceder a la observación.")

    version_key, business_key = keys[dimension]
    required_types = {
        version_key: T.LongType(),
        business_key: T.IntegerType(),
        "gold_processing_run_id": T.StringType(),
        "gold_processed_at": T.TimestampType(),
    }
    for name, expected_type in required_types.items():
        if name not in frame.columns:
            raise ValueError(f"Falta la columna: {name}")
        if frame.schema[name].dataType != expected_type:
            raise ValueError(f"Tipo incompatible: {name}")

    if not frame.limit(1).count():
        raise ValueError("Se requiere una dimensión inicial no vacía.")

    for key in (version_key, business_key):
        if frame.filter(
            F.col(key).isNull() | (F.col(key) <= 0)
        ).limit(1).count():
            raise ValueError(f"Clave nula o no positiva: {key}")

        if (
            frame.groupBy(key).count()
            .filter(F.col("count") > 1).limit(1).count()
        ):
            raise ValueError(f"Clave duplicada en la base inicial: {key}")

    invalid_provenance = (
        F.col("gold_processing_run_id").isNull()
        | (F.length(F.trim(F.col("gold_processing_run_id"))) == 0)
        | F.col("gold_processed_at").isNull()
        | (
            F.col("gold_processed_at")
            > F.lit(instants["observed_at"])
        )
    )
    if frame.filter(invalid_provenance).limit(1).count():
        raise ValueError("Procedencia Gold inválida o posterior a la observación.")

    return (
        frame
        .withColumn("valid_from", F.lit(instants["observed_at"]))
        .withColumn("valid_to", F.lit(None).cast("timestamp"))
        .withColumn("is_current", F.lit(True))
        .withColumn("scd_created_batch_id", F.lit(batch_id))
        .withColumn("scd_last_modified_batch_id", F.lit(batch_id))
        .withColumn("scd_last_modified_run_id", F.lit(run_id))
        .withColumn("scd_last_modified_at", F.lit(instants["processed_at"]))
    )
