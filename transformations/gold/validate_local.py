"""Valida Gold persistido y guarda un informe independiente."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession

from transformations.gold.validation import (
    read_gold_execution,
    validate_gold_model,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    report_path = args.report.resolve()
    if not report_path.is_file():
        parser.error(f"No existe el informe: {report_path}")

    original_bytes = report_path.read_bytes()
    validation_id = str(uuid4())
    output_path = report_path.with_name(
        f"validation-{validation_id}.json"
    )

    outcome = {
        "validation_run_id": validation_id,
        "scope": "local_gold_model_validation",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "execution_report_path": str(report_path),
        "execution_report_sha256": hashlib.sha256(
            original_bytes
        ).hexdigest(),
    }

    os.environ["PYSPARK_PYTHON"] = sys.executable
    spark = None
    cached = []

    try:
        builder = (
            SparkSession.builder
            .master("local[1]")
            .appName("arlp-m9-validate-gold")
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

        report, inputs, tables = read_gold_execution(spark, report_path)

        if report_path.read_bytes() != original_bytes:
            raise RuntimeError("El informe cambió durante su lectura.")

        outcome["gold_processing_run_id"] = report["gold_processing_run_id"]

        for frame in list(inputs.values()) + list(tables.values()):
            frame.cache()
            cached.append(frame)

        outcome["validation"] = validate_gold_model(inputs, tables, report)

        if report_path.read_bytes() != original_bytes:
            raise RuntimeError("El informe cambió durante la validación.")

        outcome["status"] = "passed"

    except Exception as error:
        outcome["status"] = "failed"
        outcome["error"] = str(error)
        raise

    finally:
        outcome["finished_at"] = datetime.now(timezone.utc).isoformat()
        try:
            with output_path.open("x", encoding="utf-8") as handle:
                json.dump(outcome, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            print("Estado de validación:", outcome["status"])
            print("Informe de validación:", output_path)
        finally:
            if spark is not None:
                try:
                    for frame in cached:
                        frame.unpersist()
                finally:
                    spark.stop()


if __name__ == "__main__":
    main()
