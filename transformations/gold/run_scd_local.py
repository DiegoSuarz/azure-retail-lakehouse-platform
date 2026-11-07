"""Ejecuta cambios SCD locales sobre una dimensión Delta existente."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

from transformations.gold.scd_transform import prepare_scd_dimension
from transformations.gold.scd_storage import (
    read_scd_dimension,
    save_scd_dimension,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dimension", choices=("dim_product", "dim_customer"), required=True
    )
    parser.add_argument("--input-path", required=True)
    parser.add_argument("--input-version", type=int, required=True)
    parser.add_argument("--target-path", required=True)
    parser.add_argument("--base-version", type=int, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--observed-at", required=True)
    args = parser.parse_args()

    try:
        observed_at = datetime.fromisoformat(args.observed_at)
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("La observación debe incluir zona horaria.")
        observed_at = observed_at.astimezone(timezone.utc)
    except ValueError as error:
        parser.error(str(error))

    processed_at = datetime.now(timezone.utc)
    if observed_at > processed_at:
        parser.error("La observación no puede estar en el futuro.")
    if args.input_version < 0 or args.base_version < 0:
        parser.error("Las versiones Delta deben ser no negativas.")
    if not args.batch_id.strip():
        parser.error("batch-id debe ser no vacío.")

    run_id = str(uuid4())
    os.environ["PYSPARK_PYTHON"] = sys.executable

    builder = (
        SparkSession.builder.master("local[1]")
        .appName("arlp-scd-local")
        .config("spark.driver.memory", "1g")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension")
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        .config("spark.databricks.delta.snapshotPartitions", "2")
    )
    spark = configure_spark_with_delta_pip(builder).getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    try:
        incoming = read_scd_dimension(
            spark, args.input_path, args.input_version
        )
        current = read_scd_dimension(
            spark, args.target_path, args.base_version
        )

        prepared = prepare_scd_dimension(
            incoming, current, args.dimension,
            args.batch_id, run_id, observed_at, processed_at,
        )
        change_counts = {
            row["change_type"]: row["count"]
            for row in prepared["changes"].groupBy("change_type").count().collect()
        }

        result = save_scd_dimension(
            prepared["dimension"], args.target_path,
            args.dimension, args.base_version,
        )

        print(json.dumps({
            "status": "completed",
            "dimension": args.dimension,
            "batch_id": args.batch_id,
            "run_id": run_id,
            "observed_at": observed_at.isoformat(),
            "processed_at": processed_at.isoformat(),
            "input": {
                "path": args.input_path,
                "version": args.input_version,
            },
            "base_version": args.base_version,
            "changes": change_counts,
            "result": result,
        }, ensure_ascii=False, indent=2))
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
