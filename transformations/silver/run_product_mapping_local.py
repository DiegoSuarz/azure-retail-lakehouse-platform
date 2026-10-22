"""Ejecuta localmente la carga del mapeo externo a Silver."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

from transformations.silver.product_mapping_transform import (
    read_product_mapping,
    validate_product_mapping,
    add_mapping_provenance,
    write_product_mapping_delta,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-file", type=Path, required=True)
    parser.add_argument("--local-products", type=Path, required=True)
    parser.add_argument("--external-products", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()

    source = args.mapping_file.resolve()
    local_path = args.local_products.resolve()
    external_path = args.external_products.resolve()

    if not source.is_file():
        parser.error("No se encontró el CSV de asociaciones.")

    for path in (local_path, external_path):
        if not (path / "_delta_log").is_dir():
            parser.error(f"No se encontró una tabla Delta: {path}")

    processing_run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)
    output = args.output_root.resolve() / f"run_id={processing_run_id}"

    for path in (local_path, external_path):
        if output.is_relative_to(path) or path.is_relative_to(output):
            parser.error("La salida debe estar separada de los catálogos.")
    if source.is_relative_to(output):
        parser.error("La salida no puede contener el archivo de entrada.")

    output.mkdir(parents=True, exist_ok=False)
    os.environ["PYSPARK_PYTHON"] = sys.executable

    builder = (
        SparkSession.builder
        .master("local[1]")
        .appName("arlp-m7-product-mapping-to-silver")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .config(
            "spark.sql.extensions",
            "io.delta.sql.DeltaSparkSessionExtension",
        )
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .config("spark.databricks.delta.snapshotPartitions", "2")
    )

    spark = configure_spark_with_delta_pip(builder).getOrCreate()

    try:
        spark.sparkContext.setLogLevel("WARN")

        mapping = read_product_mapping(spark, str(source))
        local_products = spark.read.format("delta").load(str(local_path))
        external_products = spark.read.format("delta").load(str(external_path))

        if mapping.count() == 0:
            raise ValueError("El archivo de asociaciones está vacío.")

        checks = validate_product_mapping(
            mapping, local_products, external_products,
        )
        transformed = add_mapping_provenance(
            mapping, str(source), processing_run_id, started_at,
        )
        table = write_product_mapping_delta(
            spark, transformed, str(output / "silver"),
        )

        report = {
            "status": "completed",
            "scope": "local_product_mapping_to_silver",
            "processing_run_id": processing_run_id,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "source_file": str(source),
            "local_products_path": str(local_path),
            "external_products_path": str(external_path),
            "checks": checks,
            "table": table,
        }
        report_path = output / "report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print("CONTROLES:", checks)
        print(f"PASS: {table['row_count']} asociaciones escritas y verificadas.")
        print("INFORME:", report_path)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
