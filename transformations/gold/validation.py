"""Lectura y validación del modelo Gold persistido."""

import json
from pathlib import Path

from transformations.gold.inputs import EXPECTED_ENTITIES


EXPECTED_GOLD_TABLES = {
    "dim_product",
    "dim_customer",
    "dim_date",
    "dim_order_status",
    "ref_exchange_rates",
    "product_catalog_mapping",
    "fact_sales",
}


def read_gold_execution(spark, report_path):
    """Recupera las versiones Silver y Gold registradas en una ejecución."""
    report = json.loads(
        Path(report_path).read_text(encoding="utf-8")
    )

    if (
        report.get("scope") != "local_gold_initial"
        or report.get("status") != "tables_verified"
    ):
        raise ValueError("Se requiere una ejecución con tablas verificadas.")

    specifications = {}

    for section, expected_names in (
        ("inputs", EXPECTED_ENTITIES),
        ("tables", EXPECTED_GOLD_TABLES),
    ):
        entries = report.get(section)
        if not isinstance(entries, dict) or set(entries) != expected_names:
            raise ValueError(f"Inventario incompatible: {section}")

        specifications[section] = {}

        for name, record in entries.items():
            if not isinstance(record, dict):
                raise ValueError(f"Registro incompatible: {section}/{name}")

            path = record.get("path")
            version = record.get("version")
            row_count = record.get("row_count")

            if not isinstance(path, str) or not path.strip():
                raise ValueError(f"Ruta inválida: {section}/{name}")

            if not Path(path).is_absolute():
                raise ValueError(f"Se requiere ruta absoluta: {section}/{name}")

            if type(version) is not int or version < 0:
                raise ValueError(f"Versión inválida: {section}/{name}")

            if type(row_count) is not int or row_count < 0:
                raise ValueError(f"Conteo inválido: {section}/{name}")

            if section == "tables" and record.get("verified") is not True:
                raise ValueError(f"Tabla sin verificación: {name}")

            specifications[section][name] = (path, version, row_count)

    recovered = {}

    for section, entries in specifications.items():
        recovered[section] = {}

        for name, (path, version, expected_count) in entries.items():
            frame = (
                spark.read.format("delta")
                .option("versionAsOf", version)
                .load(path)
            )

            actual_count = frame.count()
            if actual_count != expected_count:
                raise ValueError(
                    f"Conteo diferente en {section}/{name}: "
                    f"esperado={expected_count}, obtenido={actual_count}"
                )

            recovered[section][name] = frame

    return report, recovered["inputs"], recovered["tables"]


def validate_gold_relationships(tables):
    """Comprueba el grano, las claves y las referencias del modelo inicial."""
    from pyspark.sql import functions as F

    if set(tables) != EXPECTED_GOLD_TABLES:
        raise ValueError("Inventario Gold incompatible para validar relaciones.")

    unique_keys = (
        ("dim_product", ("product_key",)),
        ("dim_product", ("product_id",)),
        ("dim_customer", ("customer_key",)),
        ("dim_customer", ("customer_id",)),
        ("dim_date", ("date_key",)),
        ("dim_date", ("full_date",)),
        ("dim_order_status", ("order_status_key",)),
        ("dim_order_status", ("status",)),
        ("fact_sales", ("order_id", "line_number")),
        ("ref_exchange_rates", ("series_code", "observation_date")),
        ("product_catalog_mapping", ("source_system", "external_product_id")),
        ("product_catalog_mapping", ("source_system", "product_id")),
    )
    positive_columns = {
        "product_key", "product_id", "customer_key", "customer_id",
        "date_key", "order_status_key", "order_id", "line_number",
        "external_product_id",
    }
    checks = []

    for table_name, columns in unique_keys:
        frame = tables[table_name]
        invalid = F.lit(False)

        for column in columns:
            invalid = invalid | F.col(column).isNull()
            if column in positive_columns:
                invalid = invalid | (F.col(column) <= 0)

        invalid_count = frame.filter(invalid).count()
        duplicate_groups = (
            frame.groupBy(*columns)
            .count()
            .filter(F.col("count") > 1)
            .count()
        )

        check = {
            "table": table_name,
            "keys": list(columns),
            "invalid_key_rows": invalid_count,
            "duplicate_key_groups": duplicate_groups,
            "passed": invalid_count == 0 and duplicate_groups == 0,
        }
        checks.append(check)

        if not check["passed"]:
            raise ValueError(f"Clave Gold incompatible: {check}")

    relationships = (
        ("fact_sales", "product_key", "dim_product", "product_key"),
        ("fact_sales", "customer_key", "dim_customer", "customer_key"),
        ("fact_sales", "date_key", "dim_date", "date_key"),
        (
            "fact_sales", "order_status_key",
            "dim_order_status", "order_status_key",
        ),
        (
            "product_catalog_mapping", "product_key",
            "dim_product", "product_key",
        ),
        (
            "product_catalog_mapping", "product_id",
            "dim_product", "product_id",
        ),
    )

    for source_name, source_column, target_name, target_column in relationships:
        source = tables[source_name]
        reference = tables[target_name].select(
            F.col(target_column).alias(source_column)
        )

        missing_count = source.join(
            reference,
            on=source_column,
            how="left_anti",
        ).count()

        check = {
            "table": source_name,
            "column": source_column,
            "reference_table": target_name,
            "reference_column": target_column,
            "missing_reference_rows": missing_count,
            "passed": missing_count == 0,
        }
        checks.append(check)

        if not check["passed"]:
            raise ValueError(f"Referencia Gold inexistente: {check}")

    mismatched_products = tables["product_catalog_mapping"].select(
        "product_id", "product_key"
    ).join(
        tables["dim_product"].select("product_id", "product_key"),
        on=["product_id", "product_key"],
        how="left_anti",
    ).count()

    pair_check = {
        "table": "product_catalog_mapping",
        "rule": "product_id_matches_product_key",
        "invalid_rows": mismatched_products,
        "passed": mismatched_products == 0,
    }
    checks.append(pair_check)

    if not pair_check["passed"]:
        raise ValueError(f"Correspondencia de producto incompatible: {pair_check}")

    return {"passed": True, "checks": checks}


def validate_gold_provenance(tables, report):
    """Comprueba que todas las filas pertenezcan a la ejecución registrada."""
    from datetime import datetime, timezone

    from pyspark.sql import functions as F
    from pyspark.sql import types as T

    if set(tables) != EXPECTED_GOLD_TABLES:
        raise ValueError("Inventario Gold incompatible para validar procedencia.")

    run_id = report.get("gold_processing_run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("Identificador de ejecución inválido en el informe.")

    processed_at_text = report.get("gold_processed_at")
    if not isinstance(processed_at_text, str):
        raise ValueError("Fecha de procesamiento inválida en el informe.")

    try:
        processed_at = datetime.fromisoformat(
            processed_at_text.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(
            "Fecha de procesamiento inválida en el informe."
        ) from error

    if (
        processed_at.tzinfo is None
        or processed_at.utcoffset() is None
    ):
        raise ValueError("La fecha del informe debe incluir zona horaria.")

    processed_at_utc = processed_at.astimezone(timezone.utc)
    checks = []

    for name, frame in tables.items():
        expected_types = (
            ("gold_processing_run_id", T.StringType()),
            ("gold_processed_at", T.TimestampType()),
        )
        for column, expected_type in expected_types:
            if column not in frame.columns:
                raise ValueError(f"Columna de procedencia ausente: {name}/{column}")

            if frame.schema[column].dataType != expected_type:
                raise ValueError(f"Tipo de procedencia incompatible: {name}/{column}")

        invalid = (
            ~F.col("gold_processing_run_id").eqNullSafe(F.lit(run_id))
            | ~F.col("gold_processed_at").eqNullSafe(F.lit(processed_at_utc))
        )
        invalid_count = frame.filter(invalid).count()

        check = {
            "table": name,
            "rule": "shared_gold_provenance",
            "invalid_rows": invalid_count,
            "passed": invalid_count == 0,
        }
        checks.append(check)

        if not check["passed"]:
            raise ValueError(f"Procedencia Gold incompatible: {check}")

    return {"passed": True, "checks": checks}
