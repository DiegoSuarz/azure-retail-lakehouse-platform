"""Reglas y preparación integrada de cambios dimensionales SCD."""

from functools import reduce
from operator import or_
from pyspark.sql import functions as F
from pyspark.sql import types as T
from datetime import datetime, timezone
from pyspark.sql.window import Window


SCD_RULES = {
    "dim_product": {
        "business_key": "product_id",
        "version_key": "product_key",
        "stable": ("sku",),
        "type1": ("product_name", "brand"),
        "type2": (
            "category_id",
            "category_name",
            "list_price",
            "is_active",
        ),
    },
    "dim_customer": {
        "business_key": "customer_id",
        "version_key": "customer_key",
        "stable": (),
        "type1": ("first_name", "last_name"),
        "type2": ("city", "region", "is_active"),
    },
}


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


def prepare_type1_updates(
    incoming, dimension, dimension_name, batch_id, run_id, processed_at
):
    """Devuelve la dimensión corregida, sin realizar escrituras."""
    for name, value in (("batch_id", batch_id), ("run_id", run_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Se requiere {name} no vacío.")

    if (
        not isinstance(processed_at, datetime)
        or processed_at.tzinfo is None
        or processed_at.utcoffset() is None
    ):
        raise ValueError("processed_at debe incluir zona horaria.")
    processed_at = processed_at.astimezone(timezone.utc)

    if dimension.sparkSession.conf.get("spark.sql.session.timeZone") != "UTC":
        raise ValueError("La sesión Spark debe utilizar UTC.")

    audit_types = {
        "scd_last_modified_batch_id": T.StringType(),
        "scd_last_modified_run_id": T.StringType(),
        "scd_last_modified_at": T.TimestampType(),
    }
    for name, expected in audit_types.items():
        if name not in dimension.columns or dimension.schema[name].dataType != expected:
            raise ValueError(f"Columna de auditoría ausente o incompatible: {name}")

    changes = detect_scd_changes(incoming, dimension, dimension_name)
    rules = SCD_RULES[dimension_name]
    business_key = rules["business_key"]
    attributes = rules["type1"]

    corrections = changes.filter(
        F.col("has_type1_change")
    ).select(business_key, *attributes)

    joined = dimension.alias("stored").join(
        corrections.alias("correction"),
        F.col(f"stored.{business_key}") == F.col(f"correction.{business_key}"),
        "left",
    )

    differences = [
        ~F.col(f"stored.{name}").eqNullSafe(F.col(f"correction.{name}"))
        for name in attributes
    ]
    needs_update = (
        F.col(f"correction.{business_key}").isNotNull()
        & reduce(or_, differences, F.lit(False))
    )

    invalid_time = (
        F.col("stored.scd_last_modified_at").isNull()
        | (F.col("stored.scd_last_modified_at") > F.lit(processed_at))
    )
    if joined.filter(needs_update & invalid_time).limit(1).count():
        raise ValueError("Auditoría temporal inválida en una fila por corregir.")

    replacements = {
        name: F.col(f"correction.{name}")
        for name in attributes
    }
    replacements.update({
        "scd_last_modified_batch_id": F.lit(batch_id),
        "scd_last_modified_run_id": F.lit(run_id),
        "scd_last_modified_at": F.lit(processed_at),
    })

    return joined.select(*[
        (
            F.when(needs_update, replacements[name])
            .otherwise(F.col(f"stored.{name}"))
            .alias(name)
        )
        if name in replacements
        else F.col(f"stored.{name}")
        for name in dimension.columns
    ])


def assign_new_version_keys(changes, dimension, dimension_name):
    """Asigna claves usando cambios validados y la misma base dimensional."""
    if dimension_name not in SCD_RULES:
        raise ValueError("Dimensión no admitida para asignar claves SCD.")

    rules = SCD_RULES[dimension_name]
    business_key = rules["business_key"]
    version_key = rules["version_key"]

    candidates = changes.filter(
        F.col("change_type").isin("new", "type2", "type1_and_type2")
    ).select(
        business_key,
        "existing_version_key",
        "change_type",
    )

    maximum = dimension.agg(
        F.max(version_key).alias("maximum")
    ).first()["maximum"]
    maximum = 0 if maximum is None else maximum

    candidate_count = candidates.count()
    if maximum + candidate_count > 9223372036854775807:
        raise ValueError("Las nuevas claves exceden el rango de long.")

    position = F.row_number().over(
        Window.orderBy(business_key)
    ).cast("long")

    return candidates.withColumn(
        "new_version_key",
        F.lit(maximum).cast("long") + position,
    )


def prepare_version_closures(
    dimension, plan, dimension_name,
    batch_id, run_id, observed_at, processed_at,
):
    """Prepara cierres tipo 2 usando un plan validado sobre la misma base."""
    from datetime import datetime, timezone
    from pyspark.sql import types as T

    if dimension_name not in SCD_RULES:
        raise ValueError("Dimensión no admitida para cerrar versiones.")

    for name, value in (("batch_id", batch_id), ("run_id", run_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Se requiere {name} no vacío.")

    instants = {}
    for name, value in (
        ("observed_at", observed_at),
        ("processed_at", processed_at),
    ):
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(f"{name} debe incluir zona horaria.")
        instants[name] = value.astimezone(timezone.utc)

    observed_at = instants["observed_at"]
    processed_at = instants["processed_at"]
    if processed_at < observed_at:
        raise ValueError("El procesamiento no puede preceder a la observación.")

    if dimension.sparkSession.conf.get("spark.sql.session.timeZone") != "UTC":
        raise ValueError("La sesión Spark debe utilizar UTC.")

    required_types = {
        "valid_from": T.TimestampType(),
        "valid_to": T.TimestampType(),
        "is_current": T.BooleanType(),
        "scd_last_modified_batch_id": T.StringType(),
        "scd_last_modified_run_id": T.StringType(),
        "scd_last_modified_at": T.TimestampType(),
    }
    for name, expected in required_types.items():
        if name not in dimension.columns or dimension.schema[name].dataType != expected:
            raise ValueError(f"Columna dimensional ausente o incompatible: {name}")

    rules = SCD_RULES[dimension_name]
    business_key = rules["business_key"]
    version_key = rules["version_key"]

    closures = plan.filter(
        F.col("change_type").isin("type2", "type1_and_type2")
    ).select(business_key, "existing_version_key")

    if closures.filter(
        F.col("existing_version_key").isNull()
    ).limit(1).count():
        raise ValueError("El plan contiene un cierre sin clave de versión.")

    if (
        closures.groupBy("existing_version_key").count()
        .filter("count > 1").limit(1).count()
    ):
        raise ValueError("El plan contiene cierres duplicados.")

    matched = closures.alias("closure").join(
        dimension.alias("stored"),
        (
            F.col("closure.existing_version_key")
            == F.col(f"stored.{version_key}")
        )
        & (
            F.col(f"closure.{business_key}")
            == F.col(f"stored.{business_key}")
        ),
        "left",
    )
    invalid = (
        F.col(f"stored.{version_key}").isNull()
        | ~F.col("stored.is_current").eqNullSafe(F.lit(True))
        | F.col("stored.valid_to").isNotNull()
        | F.col("stored.valid_from").isNull()
        | (F.col("stored.valid_from") >= F.lit(observed_at))
        | F.col("stored.scd_last_modified_at").isNull()
        | (F.col("stored.scd_last_modified_at") > F.lit(processed_at))
    )
    if matched.filter(invalid).limit(1).count():
        raise ValueError("Cierre incompatible con la versión actual o sus fechas.")

    joined = dimension.alias("stored").join(
        closures.select("existing_version_key").alias("closure"),
        F.col(f"stored.{version_key}") == F.col("closure.existing_version_key"),
        "left",
    )
    needs_closure = F.col("closure.existing_version_key").isNotNull()

    replacements = {
        "valid_to": F.lit(observed_at),
        "is_current": F.lit(False),
        "scd_last_modified_batch_id": F.lit(batch_id),
        "scd_last_modified_run_id": F.lit(run_id),
        "scd_last_modified_at": F.lit(processed_at),
    }
    return joined.select(*[
        (
            F.when(needs_closure, replacements[name])
            .otherwise(F.col(f"stored.{name}"))
            .alias(name)
        )
        if name in replacements
        else F.col(f"stored.{name}")
        for name in dimension.columns
    ])


def prepare_new_versions(
    changes, plan, dimension, dimension_name,
    batch_id, run_id, observed_at, processed_at,
):
    """Construye nuevas filas desde cambios y un plan de claves validados."""
    from datetime import datetime, timezone

    if dimension_name not in SCD_RULES:
        raise ValueError("Dimensión no admitida para construir versiones.")

    for name, value in (("batch_id", batch_id), ("run_id", run_id)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Se requiere {name} no vacío.")

    instants = {}
    for name, value in (
        ("observed_at", observed_at),
        ("processed_at", processed_at),
    ):
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(f"{name} debe incluir zona horaria.")
        instants[name] = value.astimezone(timezone.utc)

    observed_at = instants["observed_at"]
    processed_at = instants["processed_at"]
    if processed_at < observed_at:
        raise ValueError("El procesamiento no puede preceder a la observación.")

    if dimension.sparkSession.conf.get("spark.sql.session.timeZone") != "UTC":
        raise ValueError("La sesión Spark debe utilizar UTC.")

    rules = SCD_RULES[dimension_name]
    business_key = rules["business_key"]
    version_key = rules["version_key"]
    attributes = rules["stable"] + rules["type1"] + rules["type2"]

    candidates = changes.filter(
        F.col("change_type").isin("new", "type2", "type1_and_type2")
    ).select(business_key, *attributes)

    assigned = candidates.join(
        plan.select(business_key, "new_version_key"),
        business_key,
        "left",
    )
    if assigned.filter(
        F.col("new_version_key").isNull()
    ).limit(1).count():
        raise ValueError("Existe una nueva versión sin clave asignada.")

    values = {
        name: F.col(name)
        for name in (business_key,) + attributes
    }
    values.update({
        version_key: F.col("new_version_key"),
        "valid_from": F.lit(observed_at),
        "valid_to": F.lit(None).cast("timestamp"),
        "is_current": F.lit(True),
        "gold_processing_run_id": F.lit(run_id),
        "gold_processed_at": F.lit(processed_at),
        "scd_created_batch_id": F.lit(batch_id),
        "scd_last_modified_batch_id": F.lit(batch_id),
        "scd_last_modified_run_id": F.lit(run_id),
        "scd_last_modified_at": F.lit(processed_at),
    })

    if set(dimension.columns) != set(values):
        raise ValueError("Las columnas dimensionales no coinciden con el contrato.")

    result = assigned.select(*[
        values[name].alias(name)
        for name in dimension.columns
    ])
    expected_types = [field.dataType for field in dimension.schema]
    actual_types = [field.dataType for field in result.schema]
    if actual_types != expected_types:
        raise ValueError("Los tipos de las nuevas versiones son incompatibles.")

    return result

def prepare_scd_dimension(
    incoming, dimension, dimension_name,
    batch_id, run_id, observed_at, processed_at,
):
    """Coordina la preparación SCD completa sin escribir tablas."""
    changes = detect_scd_changes(incoming, dimension, dimension_name)
    validate_scd_history(dimension, dimension_name)
    plan = assign_new_version_keys(changes, dimension, dimension_name)

    corrected = prepare_type1_updates(
        incoming, dimension, dimension_name, batch_id, run_id, processed_at
    )
    closed = prepare_version_closures(
        corrected, plan, dimension_name,
        batch_id, run_id, observed_at, processed_at,
    )
    new_versions = prepare_new_versions(
        changes, plan, dimension, dimension_name,
        batch_id, run_id, observed_at, processed_at,
    )

    result = closed.unionByName(new_versions)
    validate_scd_history(result, dimension_name)

    return {
        "dimension": result,
        "key_plan": plan,
        "changes": changes,
    }


def validate_scd_history(frame, dimension_name):
    """Comprueba vigencias válidas, contiguas y una versión actual por entidad."""
    if dimension_name not in SCD_RULES:
        raise ValueError("Dimensión no admitida para validar el historial.")

    business_key = SCD_RULES[dimension_name]["business_key"]
    for name, expected in (
        (business_key, T.IntegerType()),
        ("valid_from", T.TimestampType()),
        ("valid_to", T.TimestampType()),
        ("is_current", T.BooleanType()),
    ):
        if name not in frame.columns or frame.schema[name].dataType != expected:
            raise ValueError(f"Columna temporal ausente o incompatible: {name}")

    invalid = (
        F.col(business_key).isNull()
        | (F.col(business_key) <= 0)
        | F.col("valid_from").isNull()
        | ~F.col("is_current").eqNullSafe(F.col("valid_to").isNull())
        | (
            F.col("valid_to").isNotNull()
            & (F.col("valid_to") <= F.col("valid_from"))
        )
    )
    if frame.filter(invalid).limit(1).count():
        raise ValueError("El historial contiene claves o vigencias inválidas.")

    current_counts = frame.groupBy(business_key).agg(
        F.sum(F.when(F.col("is_current"), 1).otherwise(0)).alias("current_count")
    )
    if current_counts.filter("current_count <> 1").limit(1).count():
        raise ValueError("Cada entidad debe tener exactamente una versión actual.")

    sequence = Window.partitionBy(business_key).orderBy("valid_from")
    intervals = frame.select(
        business_key, "valid_from", "valid_to"
    ).withColumn(
        "next_valid_from", F.lead("valid_from").over(sequence)
    )
    if intervals.filter(
        F.col("next_valid_from").isNotNull()
        & ~F.col("valid_to").eqNullSafe(F.col("next_valid_from"))
    ).limit(1).count():
        raise ValueError("El historial contiene solapamientos o huecos.")
