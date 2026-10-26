"""Transformaciones de productos para la prueba de CDC real."""

from datetime import datetime, timezone
from decimal import Decimal

from transformations.silver.sqlserver_schemas import PRODUCTS_SCHEMA


def products_to_dataframe(spark, records):
    """Convierte registros JSON de productos al esquema comercial."""
    rows = []

    for record in records:
        row = {
            field.name: record[field.name]
            for field in PRODUCTS_SCHEMA
        }

        row["list_price"] = Decimal(row["list_price"])

        for column in ("created_at", "updated_at"):
            parsed = datetime.fromisoformat(row[column])

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)

            row[column] = parsed

        rows.append(row)

    return spark.createDataFrame(rows, schema=PRODUCTS_SCHEMA)


def initialize_products_delta(spark, records, target_path):
    """Crea la tabla Delta inicial y verifica los valores recuperados."""
    products = products_to_dataframe(spark, records)

    products.write.format("delta").mode("error").save(str(target_path))

    recovered = (
        spark.read.format("delta")
        .load(str(target_path))
        .select(*products.columns)
    )

    if (
        products.exceptAll(recovered).count() != 0
        or recovered.exceptAll(products).count() != 0
    ):
        raise ValueError("Los productos recuperados difieren de la base inicial.")

    return {
        "path": str(target_path),
        "row_count": recovered.count(),
        "verified": True,
    }


def apply_product_changes(spark, batch, target_path, provenance=None):
    """Aplica el último estado de cada producto dentro de un lote ordenado."""
    from delta.tables import DeltaTable

    if (
        batch.get("source_database") != "TechRetail_OLTP"
        or batch.get("capture_instance") != "dbo_products"
    ):
        raise ValueError("El lote no corresponde a CDC de productos.")

    events = batch["changes"]
    if not events:
        return {"event_count": 0, "affected_products": 0}

    start = bytes.fromhex(batch["after_lsn"][2:])
    end = bytes.fromhex(batch["to_lsn"][2:])

    latest = {}
    identities = set()

    ordered = sorted(
        events,
        key=lambda event: (
            bytes.fromhex(event["commit_lsn"][2:]),
            bytes.fromhex(event["sequence_value"][2:]),
        ),
    )

    for event in ordered:
        position = bytes.fromhex(event["commit_lsn"][2:])
        identity = (
            event["commit_lsn"],
            event["sequence_value"],
            event["product_id"],
        )

        if event["operation_code"] not in (1, 2, 4):
            raise ValueError("Operación CDC no admitida.")
        if not start < position <= end:
            raise ValueError("Evento fuera del intervalo del lote.")
        if identity in identities:
            raise ValueError("Identidad de cambio repetida o ambigua.")

        identities.add(identity)
        latest[event["product_id"]] = event

    records = list(latest.values())
    products = products_to_dataframe(spark, records)
    if provenance is not None:
        products = add_product_cdc_provenance(products, **provenance)

    operations = spark.createDataFrame(
        [
            (event["product_id"], event["operation_code"])
            for event in records
        ],
        "product_id int, operation_code int",
    )
    source = products.join(operations, "product_id")

    values = {
        name: f"source.{name}"
        for name in products.columns
    }

    target = DeltaTable.forPath(spark, str(target_path))
    (
        target.alias("target")
        .merge(source.alias("source"), "target.product_id = source.product_id")
        .whenMatchedDelete(condition="source.operation_code = 1")
        .whenMatchedUpdate(
            condition="source.operation_code IN (2, 4)",
            set=values,
        )
        .whenNotMatchedInsert(
            condition="source.operation_code IN (2, 4)",
            values=values,
        )
        .execute()
    )

    return {
        "event_count": len(events),
        "affected_products": len(records),
    }


def validate_application_order(batch, last_applied_lsn):
    """Comprueba que un lote continúe desde la posición aplicada."""
    start = bytes.fromhex(batch["after_lsn"][2:])
    end = bytes.fromhex(batch["to_lsn"][2:])
    current = bytes.fromhex(last_applied_lsn[2:])

    if any(len(value) != 10 for value in (start, end, current)):
        raise ValueError("Las posiciones LSN deben contener diez bytes.")

    if end < start:
        raise ValueError("El límite final del lote es anterior al inicial.")

    if start < current:
        raise ValueError(
            "Lote anterior o solapado: no se permite sobrescribir "
            "el estado ya aplicado."
        )

    if start > current:
        raise ValueError(
            "Falta un intervalo anterior: el lote no continúa "
            "desde el último LSN aplicado."
        )

    if start == end and batch["changes"]:
        raise ValueError("Un intervalo vacío no puede contener eventos.")

    return True


def apply_product_batch(spark, batch, target_path, checkpoint, provenance=None):
    """Controla orden, aplica el lote y verifica el estado final."""
    import hashlib
    import json

    fingerprint = hashlib.sha256(
        json.dumps(
            batch, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    if checkpoint["target_path"] != str(target_path):
        raise ValueError("El checkpoint pertenece a otro destino.")

    if (
        batch.get("source_database") != "TechRetail_OLTP"
        or batch.get("capture_instance") != "dbo_products"
    ):
        raise ValueError("El lote no corresponde a CDC de productos.")

    if checkpoint.get("last_batch_sha256") == fingerprint:
        if checkpoint["last_applied_lsn"] != batch["to_lsn"]:
            raise ValueError("El checkpoint del lote repetido es incoherente.")
        return {"status": "already_applied", "checkpoint": dict(checkpoint)}

    validate_application_order(batch, checkpoint["last_applied_lsn"])

    before = spark.read.format("delta").load(str(target_path))
    commercial_columns = [field.name for field in PRODUCTS_SCHEMA]
    technical_columns = [
        "source_system", "ingestion_run_id", "processing_run_id",
        "source_file", "processed_at",
    ]
    columns = commercial_columns + (
        technical_columns if provenance is not None else []
    )
    if set(before.columns) != set(columns):
        raise ValueError("Las columnas del destino no coinciden con el alcance.")

    before = before.select(*columns)
    previous_rows = before.collect()

    expected = {
        row["product_id"]: row.asDict()
        for row in previous_rows
    }
    if len(expected) != len(previous_rows):
        raise ValueError("El destino contiene claves duplicadas.")

    events = sorted(
        batch["changes"],
        key=lambda event: (
            bytes.fromhex(event["commit_lsn"][2:]),
            bytes.fromhex(event["sequence_value"][2:]),
        ),
    )
    final_events = {}
    for event in events:
        if event["operation_code"] not in (1, 2, 4):
            raise ValueError("Operación CDC no admitida.")
        final_events[event["product_id"]] = event

    remaining = []
    for key, event in final_events.items():
        if event["operation_code"] == 1:
            expected.pop(key, None)
        else:
            remaining.append(event)

    converted_frame = products_to_dataframe(spark, remaining)
    if provenance is not None:
        converted_frame = add_product_cdc_provenance(
            converted_frame, **provenance
        )

    converted = converted_frame.collect()
    for row in converted:
        expected[row["product_id"]] = row.asDict()

    expected_frame = spark.createDataFrame(
        list(expected.values()), schema=before.schema
    )

    result = apply_product_changes(spark, batch, target_path, provenance)
    current = (
        spark.read.format("delta")
        .load(str(target_path))
        .select(*columns)
    )

    if (
        expected_frame.exceptAll(current).count() != 0
        or current.exceptAll(expected_frame).count() != 0
    ):
        raise ValueError("El resultado no coincide con el estado esperado.")

    next_checkpoint = {
        "target_path": str(target_path),
        "last_applied_lsn": batch["to_lsn"],
        "last_batch_sha256": fingerprint,
    }

    return {
        "status": "applied",
        "result": result,
        "checkpoint": next_checkpoint,
    }


def add_product_cdc_provenance(
    products,
    source_file,
    ingestion_run_id,
    processing_run_id,
    processed_at,
):
    """Añade la procedencia del lote CDC a los productos preparados."""
    from pyspark.sql import functions as F

    return (
        products
        .withColumn("source_system", F.lit("sqlserver"))
        .withColumn("ingestion_run_id", F.lit(ingestion_run_id))
        .withColumn("processing_run_id", F.lit(processing_run_id))
        .withColumn("source_file", F.lit(source_file))
        .withColumn("processed_at", F.lit(processed_at))
    )
