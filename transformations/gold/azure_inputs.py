"""Lectura de entradas Silver versionadas desde ADLS Gen2."""

from urllib.parse import urlsplit

from transformations.gold.inputs import EXPECTED_ENTITIES


def read_azure_gold_inputs(spark, specifications):
    """Lee ocho tablas Delta de Silver y comprueba sus conteos."""
    if (
        not isinstance(specifications, dict)
        or set(specifications) != EXPECTED_ENTITIES
    ):
        raise ValueError("Inventario de entradas Azure incompatible.")

    for entity, record in specifications.items():
        if not isinstance(record, dict):
            raise ValueError(f"Especificación incompatible: {entity}")

        path = record.get("path")
        version = record.get("version")
        row_count = record.get("row_count")

        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"Ruta inválida: {entity}")

        parsed = urlsplit(path)
        if (
            parsed.scheme != "abfss"
            or parsed.netloc
            != "silver@starlpdevdiego01.dfs.core.windows.net"
            or not parsed.path.strip("/")
            or parsed.query
            or parsed.fragment
            or any(part in (".", "..") for part in parsed.path.split("/"))
        ):
            raise ValueError(f"Ruta Silver Azure incompatible: {entity}")

        if type(version) is not int or version < 0:
            raise ValueError(f"Versión Delta inválida: {entity}")

        if type(row_count) is not int or row_count < 0:
            raise ValueError(f"Conteo inválido: {entity}")

    frames = {}
    records = {}

    for entity, record in specifications.items():
        frame = (
            spark.read.format("delta")
            .option("versionAsOf", record["version"])
            .load(record["path"])
        )
        actual_count = frame.count()

        if actual_count != record["row_count"]:
            raise ValueError(
                f"Conteo diferente en {entity}: "
                f"esperado={record['row_count']}, obtenido={actual_count}"
            )

        frames[entity] = frame
        records[entity] = {
            "path": record["path"],
            "version": record["version"],
            "row_count": actual_count,
        }

    return frames, records
