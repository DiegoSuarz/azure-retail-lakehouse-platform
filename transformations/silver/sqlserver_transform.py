"""Lectura y transformación de la carga inicial SQL Server."""

from transformations.silver.sqlserver_schemas import SQLSERVER_SCHEMAS


def read_sqlserver_tables(spark, bronze_root):
    """Lee las cinco entidades con sus esquemas explícitos."""
    frames = {}

    for entity, schema in SQLSERVER_SCHEMAS.items():
        source = f"{bronze_root.rstrip('/')}/{entity}/dbo.{entity}.parquet"
        frames[entity] = spark.read.schema(schema).parquet(source)

    return frames


def validate_sqlserver_tables(frames):
    """Valida las cinco tablas antes de permitir su escritura."""
    from pyspark.sql import functions as F
    from transformations.silver.sqlserver_validation import (
        validate_primary_key,
        validate_foreign_keys,
        validate_business_values,
        validate_record_timestamps,
        validate_order_completeness,
    )

    results = []

    for entity, schema in SQLSERVER_SCHEMAS.items():
        frame = frames[entity]

        # Comprobar todos los campos obligatorios.
        null_counts = frame.agg(*[
            F.count(
                F.when(F.col(field.name).isNull(), 1)
            ).alias(field.name)
            for field in schema
            if not field.nullable
        ]).first().asDict()

        results.append({
            "entity": entity,
            "rule": "required_fields",
            "null_counts": null_counts,
            "passed": all(count == 0 for count in null_counts.values()),
        })

        results.append(validate_primary_key(frame, entity))
        results.extend(validate_business_values(frame, entity))
        results.append(validate_record_timestamps(frame, entity))

    # Detenerse antes de los JOIN si fallan los controles por tabla.
    failures = [result for result in results if not result["passed"]]
    if failures:
        raise ValueError(f"Controles por tabla incumplidos: {failures}")

    results.extend(validate_foreign_keys(frames))
    results.append(validate_order_completeness(frames))

    failures = [result for result in results if not result["passed"]]
    if failures:
        raise ValueError(f"Controles entre tablas incumplidos: {failures}")

    return results


def add_sqlserver_provenance(
    frames, bronze_root, ingestion_run_id, processing_run_id, processed_at
):
    """Añade procedencia conservando las columnas comerciales."""
    from pyspark.sql import functions as F

    transformed = {}

    for entity, frame in frames.items():
        source = f"{bronze_root.rstrip('/')}/{entity}/dbo.{entity}.parquet"

        transformed[entity] = (
            frame
            .withColumn("source_system", F.lit("sqlserver"))
            .withColumn("ingestion_run_id", F.lit(ingestion_run_id))
            .withColumn("processing_run_id", F.lit(processing_run_id))
            .withColumn("source_file", F.lit(source))
            .withColumn("processed_at", F.lit(processed_at))
        )

    return transformed


def write_sqlserver_delta(spark, frames, silver_root):
    """Escribe las tablas Delta y comprueba los datos recuperados."""
    results = []

    for entity, frame in frames.items():
        target = f"{silver_root.rstrip('/')}/techretail/{entity}"

        frame.write.format("delta").mode("error").save(target)

        recovered = (
            spark.read.format("delta")
            .load(target)
            .select(*frame.columns)
        )

        expected_types = [
            (field.name, field.dataType) for field in frame.schema
        ]
        actual_types = [
            (field.name, field.dataType) for field in recovered.schema
        ]
        if actual_types != expected_types:
            raise ValueError(f"{entity}: tipos diferentes después de escribir")

        if (
            frame.exceptAll(recovered).count() != 0
            or recovered.exceptAll(frame).count() != 0
        ):
            raise ValueError(f"{entity}: datos diferentes después de escribir")

        results.append({
            "entity": entity,
            "path": target,
            "row_count": recovered.count(),
            "verified": True,
        })

    return results
