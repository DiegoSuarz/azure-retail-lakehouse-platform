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
