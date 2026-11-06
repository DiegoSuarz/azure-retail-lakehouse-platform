"""Huellas deterministas del contenido de entrada SCD."""

import hashlib
import json

from pyspark.sql import functions as F
from pyspark.sql import types as T

from transformations.gold.scd_rules import SCD_RULES


def fingerprint_scd_input(incoming, dimension_name):
    """Calcula SHA-256 de atributos, tipos y filas sin depender de su orden."""
    if dimension_name not in SCD_RULES:
        raise ValueError("Dimensión no admitida para calcular la huella.")

    if len(incoming.columns) != len(set(incoming.columns)):
        raise ValueError("La entrada contiene nombres de columna duplicados.")

    rules = SCD_RULES[dimension_name]
    columns = (
        (rules["business_key"],)
        + rules["stable"] + rules["type1"] + rules["type2"]
    )
    missing = set(columns) - set(incoming.columns)
    if missing:
        raise ValueError(f"Faltan columnas para calcular la huella: {sorted(missing)}")

    supported_types = (
        T.IntegerType, T.LongType, T.StringType,
        T.BooleanType, T.DecimalType,
    )
    for name in columns:
        if not isinstance(incoming.schema[name].dataType, supported_types):
            raise ValueError(f"Tipo no admitido para la huella SCD: {name}")

    header = {
        "format_version": 1,
        "dimension": dimension_name,
        "columns": [
            [name, incoming.schema[name].dataType.simpleString()]
            for name in columns
        ],
    }
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            header, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )
    digest.update(b"\n")

    row_json = F.to_json(
        F.struct(*[F.col(name).alias(name) for name in columns]),
        options={"ignoreNullFields": "false"},
    )
    row_hashes = incoming.select(
        F.sha2(row_json, 256).alias("row_hash")
    ).orderBy("row_hash")

    row_count = 0
    for row in row_hashes.toLocalIterator():
        digest.update(row["row_hash"].encode("ascii"))
        row_count += 1

    return {
        "format_version": 1,
        "sha256": digest.hexdigest(),
        "row_count": row_count,
        "columns": header["columns"],
    }
