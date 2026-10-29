"""Lectura de entradas Silver versionadas para Gold local."""

import json
from pathlib import Path


EXPECTED_ENTITIES = {
    "categories",
    "products",
    "customers",
    "orders",
    "order_items",
    "dummyjson_products",
    "product_external_mapping",
    "exchange_rates",
}


def read_gold_inputs(spark, manifest_path, repository_root):
    """Lee versiones Delta explícitas y comprueba sus conteos."""
    root = Path(repository_root).resolve()
    manifest = json.loads(
        Path(manifest_path).read_text(encoding="utf-8")
    )

    if (
        type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
        or manifest.get("scope") != "local_gold_initial_inputs"
        or manifest.get("path_base") != "repository_root"
    ):
        raise ValueError("Contrato del inventario Gold incompatible.")

    tables = manifest.get("tables")
    if not isinstance(tables, dict) or set(tables) != EXPECTED_ENTITIES:
        raise ValueError("Inventario de entidades Silver incompatible.")

    specifications = {}

    for entity, specification in tables.items():
        if not isinstance(specification, dict):
            raise ValueError(f"Especificación incompatible: {entity}")

        relative_path = specification.get("path")
        version = specification.get("version")
        expected_count = specification.get("row_count")

        if not isinstance(relative_path, str) or not relative_path.strip():
            raise ValueError(f"Ruta no válida: {entity}")

        if Path(relative_path).is_absolute():
            raise ValueError(f"La ruta debe ser relativa: {entity}")

        path = (root / relative_path).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"La ruta queda fuera del repositorio: {entity}")

        if not (path / "_delta_log").is_dir():
            raise ValueError(f"No existe la tabla Delta: {entity}")

        if type(version) is not int or version < 0:
            raise ValueError(f"Versión Delta no válida: {entity}")

        if type(expected_count) is not int or expected_count < 0:
            raise ValueError(f"Conteo de referencia no válido: {entity}")

        specifications[entity] = (path, version, expected_count)

    frames = {}
    input_records = {}

    for entity, (path, version, expected_count) in specifications.items():
        frame = (
            spark.read.format("delta")
            .option("versionAsOf", version)
            .load(str(path))
        )

        actual_count = frame.count()
        if actual_count != expected_count:
            raise ValueError(
                f"Conteo diferente en {entity}: "
                f"esperado={expected_count}, obtenido={actual_count}"
            )

        frames[entity] = frame
        input_records[entity] = {
            "path": str(path),
            "version": version,
            "row_count": actual_count,
        }

    return frames, input_records
