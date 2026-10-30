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
        "--manifest",
        type=Path,
        default=Path("data/validation/gold_initial_inputs.json"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("data/validation/gold"),
    )
    args = parser.parse_args()

    repository_root = Path(__file__).resolve().parents[2]
    manifest_path = args.manifest.resolve()
    if not manifest_path.is_file():
        parser.error(f"No existe el inventario: {manifest_path}")

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
        "manifest_path": str(manifest_path),
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
            spark, manifest_path, repository_root
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
