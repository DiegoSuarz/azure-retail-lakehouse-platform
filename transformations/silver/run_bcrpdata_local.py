"""Ejecuta localmente la carga de tasas BCRPData a Silver."""

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession, functions as F

from transformations.silver.bcrpdata_transform import (
    read_bcrpdata_observations,
    normalize_bcrpdata_observations,
    validate_bcrpdata_observations,
    write_bcrpdata_delta,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--ingestion-run-id", required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    args = parser.parse_args()

    bronze_root = args.bronze_root.resolve()
    source = bronze_root / "response.json"
    metadata_path = bronze_root / "response.json.metadata.json"

    if not source.is_file() or not metadata_path.is_file():
        parser.error("Falta la respuesta o su archivo de metadatos.")
    if bronze_root.name != f"run_id={args.ingestion_run_id}":
        parser.error("La ruta Bronze no coincide con ingestion-run-id.")
    if args.start_date > args.end_date:
        parser.error("El inicio debe ser anterior o igual al final.")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata["ingestion_run_id"] != args.ingestion_run_id:
        parser.error("Los metadatos corresponden a otra ingesta.")

    expected_url = (
        "https://estadisticas.bcrp.gob.pe/estadisticas/series/api/"
        f"PD04638PD/json/{args.start_date}/{args.end_date}/esp"
    )
    if metadata["request_url"] != expected_url:
        parser.error("La serie o el intervalo no coinciden con la extracción.")

    extracted_at = datetime.fromisoformat(metadata["extracted_at"])
    if extracted_at.tzinfo is None or extracted_at.utcoffset() is None:
        parser.error("extracted_at debe incluir zona horaria.")

    processing_run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)
    output = args.output_root.resolve() / f"run_id={processing_run_id}"

    if output.is_relative_to(bronze_root) or bronze_root.is_relative_to(output):
        parser.error("La salida debe estar separada de la entrada Bronze.")

    output.mkdir(parents=True, exist_ok=False)
    os.environ["PYSPARK_PYTHON"] = sys.executable

    builder = (
        SparkSession.builder
        .master("local[1]")
        .appName("arlp-m7-bcrpdata-to-silver")
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

        raw = read_bcrpdata_observations(spark, str(source))
        input_count = raw.count()
        if input_count == 0:
            raise ValueError("La entrada no contiene observaciones.")

        normalized = normalize_bcrpdata_observations(
            observations=raw,
            series_code="PD04638PD",
            start_date=args.start_date,
            end_date=args.end_date,
            ingestion_run_id=args.ingestion_run_id,
            processing_run_id=processing_run_id,
            extracted_at=extracted_at,
            processed_at=started_at,
        )
        checks = validate_bcrpdata_observations(
            normalized, args.start_date, args.end_date
        )

        counts = normalized.agg(
            F.count("*").alias("total"),
            F.count(F.when(F.col("available"), 1)).alias("available"),
            F.count(F.when(~F.col("available"), 1)).alias("unavailable"),
        ).first().asDict()

        if counts["total"] != input_count:
            raise ValueError("La normalización cambió la cantidad de filas.")

        result = write_bcrpdata_delta(
            spark, normalized, str(output / "silver")
        )

        report = {
            "status": "completed",
            "scope": "local_bcrpdata_to_silver",
            "ingestion_run_id": args.ingestion_run_id,
            "processing_run_id": processing_run_id,
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "source_file": str(source),
            "series_code": "PD04638PD",
            "start_date": args.start_date.isoformat(),
            "end_date": args.end_date.isoformat(),
            "extracted_at": extracted_at.isoformat(),
            "checks": checks,
            "counts": counts,
            "table": result,
        }
        report_path = output / "report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print("CONTROLES:", checks)
        print("CONTEOS:", counts)
        print(f"PASS: {result['row_count']} observaciones escritas y verificadas.")
        print("INFORME:", report_path)

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
