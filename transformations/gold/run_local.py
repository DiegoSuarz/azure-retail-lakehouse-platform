"""Construye y escribe las siete tablas Gold en Delta local."""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

from transformations.gold.build import build_gold_tables
from transformations.gold.inputs import read_gold_inputs
from transformations.gold.storage import write_verified_gold_table


# Entradas de la carga local aceptada: rutas relativas al repositorio.
SQLSERVER_SILVER = (
    "data/validation/silver_sqlserver/"
    "run_id=52af9f2c-fb55-45c9-ba54-991e5dba4fc2/"
    "silver/techretail"
)

INPUT_TABLES = {
    "categories": {
        "path": f"{SQLSERVER_SILVER}/categories",
        "version": 0,
        "row_count": 6,
    },
    "customers": {
        "path": f"{SQLSERVER_SILVER}/customers",
        "version": 0,
        "row_count": 500,
    },
    "orders": {
        "path": f"{SQLSERVER_SILVER}/orders",
        "version": 0,
        "row_count": 2000,
    },
    "order_items": {
        "path": f"{SQLSERVER_SILVER}/order_items",
        "version": 0,
        "row_count": 5862,
    },
    "products": {
        "path": "data/validation/cdc_products/silver/products",
        "version": 4,
        "row_count": 61,
    },
    "dummyjson_products": {
        "path": (
            "data/validation/silver_dummyjson/"
            "run_id=e53042a4-f37f-4481-a27f-7cf83bea82ae/"
            "silver/external/dummyjson_products"
        ),
        "version": 0,
        "row_count": 38,
    },
    "product_external_mapping": {
        "path": (
            "data/validation/silver_product_mapping/"
            "run_id=cf0fd697-681d-4e44-ac2d-66ec8d01e396/"
            "silver/reference/product_external_mapping"
        ),
        "version": 0,
        "row_count": 6,
    },
    "exchange_rates": {
        "path": (
            "data/validation/silver_bcrpdata/"
            "run_id=7ce7eb97-03c9-4027-b6c7-cec45d833eb5/"
            "silver/reference/exchange_rates"
        ),
        "version": 0,
        "row_count": 195,
    },
}


def save_report(report, path):
    """Sustituye el informe mediante un archivo temporal."""
    temporary = path.with_name(f".report-{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/validation/gold"),
    )
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[2]

    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)
    run_root = args.output_root.resolve() / f"run_id={run_id}"
    run_root.mkdir(parents=True, exist_ok=False)
    report_path = run_root / "report.json"

    report = {
        "status": "running",
        "scope": "local_gold_initial",
        "gold_processing_run_id": run_id,
        "gold_processed_at": started_at.isoformat(),
        "inputs": {},
        "tables": {},
        "model_validation": "pending",
    }
    save_report(report, report_path)

    os.environ["PYSPARK_PYTHON"] = sys.executable
    spark = None
    cached = []

    try:
        builder = (
            SparkSession.builder
            .master("local[1]")
            .appName("arlp-m9-gold-local")
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
        spark.sparkContext.setLogLevel("WARN")

        inputs, records = read_gold_inputs(
            spark, INPUT_TABLES, repository_root
        )
        report["inputs"] = records
        save_report(report, report_path)

        tables = build_gold_tables(inputs, run_id, started_at)

        for name, frame in tables.items():
            frame.cache()
            cached.append(frame)

            target = str(run_root / "tables" / name)
            result = write_verified_gold_table(spark, frame, target)
            report["tables"][name] = result
            save_report(report, report_path)
            print(f"PASS: {name}, {result['row_count']} filas verificadas.")

        report["status"] = "tables_verified"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_report(report, report_path)
        print("Informe:", report_path)

    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_report(report, report_path)
        raise

    finally:
        if spark is not None:
            try:
                for frame in cached:
                    frame.unpersist()
            finally:
                spark.stop()


if __name__ == "__main__":
    main()
