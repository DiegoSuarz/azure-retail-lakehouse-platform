"""Aplica un lote CDC de productos a Delta local con checkpoint."""

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

from ingestion.sqlserver.extract_products_cdc import save_product_changes
from transformations.silver.products_cdc_transform import apply_product_batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    args = parser.parse_args()

    batch_path = args.batch.resolve()
    target = args.target.resolve()
    checkpoint_path = args.checkpoint.resolve()

    for path in (batch_path, checkpoint_path):
        if not path.is_file():
            parser.error(f"No se encontró el archivo: {path}")

    if not (target / "_delta_log").is_dir():
        parser.error("El destino debe ser una tabla Delta existente.")
    if checkpoint_path == batch_path or checkpoint_path.is_relative_to(target):
        parser.error("El checkpoint debe estar separado del lote y de la tabla.")

    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    checkpoint_text = checkpoint_path.read_text(encoding="utf-8")
    checkpoint = json.loads(checkpoint_text)

    os.environ["PYSPARK_PYTHON"] = sys.executable

    builder = (
        SparkSession.builder
        .master("local[1]")
        .appName("arlp-m8-products-cdc")
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
        result = apply_product_batch(spark, batch, str(target), checkpoint)

        if result["status"] == "already_applied":
            print("PASS: lote ya aplicado; sin MERGE ni cambio de checkpoint.")
            return

        if checkpoint_path.read_text(encoding="utf-8") != checkpoint_text:
            raise RuntimeError(
                "El checkpoint cambió durante la ejecución. Revisar recuperación."
            )

        temporary = checkpoint_path.with_name(
            f".application-checkpoint-{uuid4().hex}.tmp"
        )
        try:
            save_product_changes(result["checkpoint"], temporary)
            os.replace(temporary, checkpoint_path)
        finally:
            temporary.unlink(missing_ok=True)

        print("PASS: lote aplicado y datos verificados.")
        print("PASS: checkpoint de aplicación actualizado.")
        print("Último LSN aplicado:", result["checkpoint"]["last_applied_lsn"])
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
