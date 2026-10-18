"""Ejecuta la carga inicial SQL Server a Delta en el entorno local."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

from transformations.silver.sqlserver_transform import (
    read_sqlserver_tables,
    validate_sqlserver_tables,
    add_sqlserver_provenance,
    write_sqlserver_delta,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--ingestion-run-id", required=True)
    args = parser.parse_args()

    bronze_root = args.bronze_root.resolve()
    if bronze_root.name != f"run_id={args.ingestion_run_id}":
        parser.error("La ruta Bronze no coincide con ingestion-run-id.")

    processing_run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)
    output = args.output_root.resolve() / f"run_id={processing_run_id}"

    if (
        output.is_relative_to(bronze_root)
        or bronze_root.is_relative_to(output)
    ):
        parser.error("La salida debe estar separada de la entrada Bronze.")

    output.mkdir(parents=True, exist_ok=False)
    silver_root = str(output / "silver")

    os.environ["PYSPARK_PYTHON"] = sys.executable

    builder = (
        SparkSession.builder
        .master("local[1]")
        .appName("arlp-m7-sqlserver-to-silver")
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

        frames = read_sqlserver_tables(spark, str(bronze_root))
        checks = validate_sqlserver_tables(frames)

        transformed = add_sqlserver_provenance(
            frames, str(bronze_root), args.ingestion_run_id,
            processing_run_id, started_at,
        )
        tables = write_sqlserver_delta(spark, transformed, silver_root)

        report = {
            "status": "completed",
            "scope": "local_sqlserver_initial_to_silver",
            "ingestion_run_id": args.ingestion_run_id,
            "processing_run_id": processing_run_id,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "bronze_root": str(bronze_root),
            "silver_root": silver_root,
            "checks": checks,
            "tables": tables,
        }
        report_path = output / "report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print(f"PASS: {len(checks)} controles previos.")
        for table in tables:
            print(f"PASS: {table['entity']}, {table['row_count']} filas.")
        print("INFORME:", report_path)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
