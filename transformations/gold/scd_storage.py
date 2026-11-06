"""Lectura y escritura de dimensiones SCD en Delta."""

from functools import reduce
from operator import and_

from delta.tables import DeltaTable
from pyspark.sql import functions as F

from transformations.gold.scd_transform import SCD_RULES


def read_scd_dimension(spark, path, version):
    """Lee una versión Delta explícita."""
    if type(version) is not int or version < 0:
        raise ValueError("Se requiere una versión Delta no negativa.")

    return (
        spark.read.format("delta")
        .option("versionAsOf", version)
        .load(path)
    )


def _same_data(left, right):
    """Compara valores y repeticiones con columnas en el mismo orden."""
    return (
        not left.exceptAll(right).limit(1).count()
        and not right.exceptAll(left).limit(1).count()
    )


def save_scd_dimension(prepared, path, dimension_name, base_version):
    """Aplica un resultado completo sobre la versión de partida esperada."""
    if dimension_name not in SCD_RULES:
        raise ValueError("Dimensión no admitida para guardar.")

    spark = prepared.sparkSession
    table = DeltaTable.forPath(spark, path)
    current_version = table.history(1).first()["version"]
    if current_version != base_version:
        raise ValueError("El destino cambió; revisar antes de aplicar el lote.")

    current = read_scd_dimension(spark, path, base_version)
    expected_schema = [(field.name, field.dataType) for field in current.schema]
    actual_schema = [(field.name, field.dataType) for field in prepared.schema]
    if actual_schema != expected_schema:
        raise ValueError("El esquema preparado difiere del destino.")

    rules = SCD_RULES[dimension_name]
    version_key = rules["version_key"]
    business_key = rules["business_key"]

    if prepared.filter(
        F.col(version_key).isNull() | (F.col(version_key) <= 0)
    ).limit(1).count():
        raise ValueError("El resultado contiene claves de versión inválidas.")

    if prepared.groupBy(version_key).count().filter("count > 1").limit(1).count():
        raise ValueError("El resultado contiene claves de versión duplicadas.")

    preserved_columns = [
        version_key, business_key,
        "gold_processing_run_id", "gold_processed_at",
        "scd_created_batch_id",
    ]
    if current.select(*preserved_columns).exceptAll(
        prepared.select(*preserved_columns)
    ).limit(1).count():
        raise ValueError("Se eliminaron claves o se alteró su identidad de creación.")

    expected = prepared.cache()
    try:
        row_count = expected.count()
        if _same_data(current, expected):
            return {
                "path": path, "version": base_version,
                "row_count": row_count, "changed": False, "verified": True,
            }

        equal_values = reduce(and_, [
            F.col(f"stored.{name}").eqNullSafe(F.col(f"incoming.{name}"))
            for name in current.columns
        ])
        (
            table.alias("stored")
            .merge(
                expected.alias("incoming"),
                F.col(f"stored.{version_key}") == F.col(f"incoming.{version_key}"),
            )
            .whenMatchedUpdateAll(condition=~equal_values)
            .whenNotMatchedInsertAll()
            .execute()
        )

        result_version = table.history(1).first()["version"]
        if result_version != base_version + 1:
            raise ValueError("Versión resultante inesperada; revisar la escritura.")

        recovered = read_scd_dimension(spark, path, result_version)
        if not _same_data(expected, recovered):
            raise ValueError("El resultado persistido difiere del preparado.")

        return {
            "path": path, "version": result_version,
            "row_count": row_count, "changed": True, "verified": True,
        }
    finally:
        expected.unpersist()
