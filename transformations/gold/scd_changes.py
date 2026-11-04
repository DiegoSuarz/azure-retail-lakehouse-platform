"""Validación de entradas y detección de cambios SCD."""

from functools import reduce
from operator import or_

from pyspark.sql import functions as F
from pyspark.sql import types as T

from transformations.gold.scd_rules import SCD_RULES


RESULT_COLUMNS = (
    "existing_version_key",
    "has_type1_change",
    "has_type2_change",
    "change_type",
)


def _validate_inputs(incoming, dimension, rules):
    """Comprueba que la comparación sea válida y no multiplique entidades."""
    business_key = rules["business_key"]
    version_key = rules["version_key"]
    attributes = rules["stable"] + rules["type1"] + rules["type2"]
    required = (business_key,) + attributes

    for label, frame in (("entrada", incoming), ("dimensión", dimension)):
        if len(frame.columns) != len(set(frame.columns)):
            raise ValueError(f"Columnas duplicadas en {label}.")
        missing = set(required) - set(frame.columns)
        if missing:
            raise ValueError(f"Faltan columnas en {label}: {sorted(missing)}")
        if frame.schema[business_key].dataType != T.IntegerType():
            raise ValueError(f"Tipo incompatible de {business_key} en {label}.")
        if frame.filter(
            F.col(business_key).isNull() | (F.col(business_key) <= 0)
        ).limit(1).count():
            raise ValueError(f"Clave de negocio inválida en {label}.")

    if set(RESULT_COLUMNS).intersection(incoming.columns):
        raise ValueError("La entrada contiene columnas reservadas.")

    for name in required:
        if incoming.schema[name].dataType != dimension.schema[name].dataType:
            raise ValueError(f"Tipos incompatibles para comparar {name}.")

    for name, expected in (
        (version_key, T.LongType()),
        ("is_current", T.BooleanType()),
        ("valid_to", T.TimestampType()),
    ):
        if name not in dimension.columns or dimension.schema[name].dataType != expected:
            raise ValueError(f"Columna dimensional ausente o incompatible: {name}")

    invalid_version = (
        F.col(version_key).isNull()
        | (F.col(version_key) <= 0)
        | ~F.col("is_current").eqNullSafe(F.col("valid_to").isNull())
    )
    if dimension.filter(invalid_version).limit(1).count():
        raise ValueError("Clave de versión o estado de vigencia inválido.")

    current = dimension.filter(F.col("is_current"))
    for label, frame, key in (
        ("entrada", incoming, business_key),
        ("historial", dimension, version_key),
        ("versiones actuales", current, business_key),
    ):
        if frame.groupBy(key).count().filter("count > 1").limit(1).count():
            raise ValueError(f"Clave duplicada en {label}: {key}")

    if dimension.select(business_key).distinct().join(
        current.select(business_key), business_key, "left_anti"
    ).limit(1).count():
        raise ValueError("Existe una entidad sin versión actual.")

    return current


def _attributes_changed(names):
    """Devuelve true si algún atributo difiere, incluyendo cambios de NULL."""
    differences = [
        ~F.col(f"incoming.{name}").eqNullSafe(F.col(f"current.{name}"))
        for name in names
    ]
    return reduce(or_, differences, F.lit(False))


def detect_scd_changes(incoming, dimension, dimension_name):
    """Clasifica las entidades recibidas frente a su versión actual."""
    if dimension_name not in SCD_RULES:
        raise ValueError("Dimensión no admitida para detección SCD.")

    rules = SCD_RULES[dimension_name]
    current = _validate_inputs(incoming, dimension, rules)
    business_key = rules["business_key"]
    version_key = rules["version_key"]

    comparison = incoming.alias("incoming").join(
        current.alias("current"),
        F.col(f"incoming.{business_key}") == F.col(f"current.{business_key}"),
        "left",
    )
    exists = F.col(f"current.{version_key}").isNotNull()

    if comparison.filter(
        exists & _attributes_changed(rules["stable"])
    ).limit(1).count():
        raise ValueError("Cambió un atributo estable de una entidad existente.")

    type1 = exists & _attributes_changed(rules["type1"])
    type2 = exists & _attributes_changed(rules["type2"])
    change_type = (
        F.when(~exists, "new")
        .when(type1 & type2, "type1_and_type2")
        .when(type1, "type1")
        .when(type2, "type2")
        .otherwise("unchanged")
    )

    return comparison.select(
        "incoming.*",
        F.col(f"current.{version_key}").alias("existing_version_key"),
        type1.alias("has_type1_change"),
        type2.alias("has_type2_change"),
        change_type.alias("change_type"),
    )
