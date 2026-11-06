"""Huellas deterministas del contenido de entrada SCD."""

import hashlib
import json

from pyspark.sql import functions as F
from pyspark.sql import types as T

from transformations.gold.scd_transform import SCD_RULES


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


def build_scd_batch_identity(
    incoming, dimension_name, batch_id, observed_at,
    source_references, rules_version,
):
    """Construye una identidad estable del lote, independiente del intento."""
    from datetime import datetime, timezone

    expected_sources = {
        "dim_product": {"products", "categories"},
        "dim_customer": {"customers"},
    }
    if dimension_name not in expected_sources:
        raise ValueError("Dimensión no admitida para identificar el lote.")

    for name, value in (
        ("batch_id", batch_id),
        ("rules_version", rules_version),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Se requiere {name} no vacío.")

    if (
        not isinstance(observed_at, datetime)
        or observed_at.tzinfo is None
        or observed_at.utcoffset() is None
    ):
        raise ValueError("observed_at debe incluir zona horaria.")

    observed_utc = observed_at.astimezone(timezone.utc).isoformat(
        timespec="microseconds"
    )

    if (
        not isinstance(source_references, dict)
        or set(source_references) != expected_sources[dimension_name]
    ):
        raise ValueError("Las referencias de origen no corresponden a la dimensión.")

    references = {}
    for name, specification in source_references.items():
        if (
            not isinstance(specification, dict)
            or set(specification) != {"path", "version"}
        ):
            raise ValueError(f"Referencia incompatible: {name}")

        path = specification["path"]
        version = specification["version"]
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"Ruta de origen inválida: {name}")
        if type(version) is not int or version < 0:
            raise ValueError(f"Versión Delta inválida: {name}")

        references[name] = {"path": path, "version": version}

    payload = {
        "identity_format_version": 1,
        "batch_id": batch_id,
        "dimension": dimension_name,
        "observed_at": observed_utc,
        "sources": references,
        "input": fingerprint_scd_input(incoming, dimension_name),
        "rules_version": rules_version,
        "rules": SCD_RULES[dimension_name],
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )

    return {
        "sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "payload": json.loads(serialized),
    }
