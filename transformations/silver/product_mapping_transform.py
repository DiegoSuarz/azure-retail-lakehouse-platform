"""Lectura y transformación del mapeo educativo de productos."""

from pyspark.sql import types as T


MAPPING_SCHEMA = T.StructType([
    T.StructField("source_system", T.StringType(), nullable=True),
    T.StructField("external_product_id", T.IntegerType(), nullable=True),
    T.StructField("product_id", T.IntegerType(), nullable=True),
    T.StructField("mapping_type", T.StringType(), nullable=True),
    T.StructField("mapping_note", T.StringType(), nullable=True),
])


def read_product_mapping(spark, source_path):
    """Lee el CSV de asociaciones con tipos explícitos."""
    return (
        spark.read
        .schema(MAPPING_SCHEMA)
        .option("header", True)
        .option("enforceSchema", False)
        .option("encoding", "UTF-8")
        .option("mode", "FAILFAST")
        .csv(source_path)
    )


def validate_product_mapping(mapping, local_products, external_products):
    """Comprueba asociaciones y referencias a ambos catálogos."""
    from pyspark.sql import functions as F

    valid = (
        (F.col("source_system") == "dummyjson")
        & (F.col("external_product_id") > 0)
        & (F.col("product_id") > 0)
        & (F.col("mapping_type") == "synthetic_demo")
        & (F.length(F.trim(F.col("mapping_note"))) > 0)
    )

    invalid_rows = mapping.filter(
        ~F.coalesce(valid, F.lit(False))
    ).count()

    duplicate_local = (
        mapping.groupBy("source_system", "product_id")
        .count()
        .filter(F.col("count") > 1)
        .count()
    )
    duplicate_external = (
        mapping.groupBy("source_system", "external_product_id")
        .count()
        .filter(F.col("count") > 1)
        .count()
    )

    missing_local = mapping.join(
        local_products.select("product_id"),
        on="product_id",
        how="left_anti",
    ).count()

    missing_external = mapping.join(
        external_products.select("source_system", "external_product_id"),
        on=["source_system", "external_product_id"],
        how="left_anti",
    ).count()

    result = {
        "invalid_rows": invalid_rows,
        "duplicate_local_groups": duplicate_local,
        "duplicate_external_groups": duplicate_external,
        "missing_local_rows": missing_local,
        "missing_external_rows": missing_external,
    }
    result["passed"] = all(count == 0 for count in result.values())

    if not result["passed"]:
        raise ValueError(f"Mapeo de productos incompatible: {result}")

    return result


def add_mapping_provenance(
    mapping, source_path, processing_run_id, processed_at
):
    """Añade procedencia del archivo de referencia versionado."""
    from pyspark.sql import functions as F

    return (
        mapping
        .withColumn("source_file", F.lit(source_path))
        .withColumn("processing_run_id", F.lit(processing_run_id))
        .withColumn("processed_at", F.lit(processed_at))
    )


def write_product_mapping_delta(spark, mapping, silver_root):
    """Escribe las asociaciones y verifica tipos y valores."""
    target = f"{silver_root.rstrip('/')}/reference/product_external_mapping"

    mapping.write.format("delta").mode("error").save(target)

    recovered = (
        spark.read.format("delta")
        .load(target)
        .select(*mapping.columns)
    )

    expected_types = [
        (field.name, field.dataType) for field in mapping.schema
    ]
    actual_types = [
        (field.name, field.dataType) for field in recovered.schema
    ]
    if actual_types != expected_types:
        raise ValueError("Mapeo: tipos diferentes después de escribir")

    if (
        mapping.exceptAll(recovered).count() != 0
        or recovered.exceptAll(mapping).count() != 0
    ):
        raise ValueError("Mapeo: datos diferentes después de escribir")

    return {
        "entity": "product_external_mapping",
        "path": target,
        "row_count": recovered.count(),
        "verified": True,
    }
