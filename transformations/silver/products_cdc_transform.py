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


def apply_product_changes(spark, batch, target_path):
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
    operations = spark.createDataFrame(
        [
            (event["product_id"], event["operation_code"])
            for event in records
        ],
        "product_id int, operation_code int",
    )
    source = products.join(operations, "product_id")

    values = {
        field.name: f"source.{field.name}"
        for field in PRODUCTS_SCHEMA
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
