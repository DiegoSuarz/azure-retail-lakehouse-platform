"""Inicializa copias locales SCD desde una carga Gold validada."""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from delta import configure_spark_with_delta_pip
from pyspark.sql import SparkSession, functions as F

from transformations.gold.run_local import save_report
from transformations.gold.scd_initialization import initialize_scd_dimension
from transformations.gold.storage import write_verified_gold_table


def require(condition, message):
    """Detiene la ejecución si incumple el contrato."""
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--observed-at", required=True)
    args = parser.parse_args()

    repository = Path(__file__).resolve().parents[2]
    batch_id = args.batch_id
    require(str(UUID(batch_id)) == batch_id, "batch_id incompatible.")

    batch_root = repository / "data/validation/scd" / f"batch_id={batch_id}"
    require(
        batch_root.resolve() == batch_root,
        "Carpeta del lote incompatible.",
    )

    observed_at = datetime.fromisoformat(args.observed_at)
    require(
        observed_at.tzinfo is not None
        and observed_at.utcoffset() is not None,
        "La observación debe incluir zona horaria.",
    )
    observed_at = observed_at.astimezone(timezone.utc)

    execution_path = args.report.resolve()
    validation_path = args.validation.resolve()
    gold_root = (repository / "data/validation/gold").resolve()
    require(
        execution_path.is_relative_to(gold_root)
        and validation_path.parent == execution_path.parent,
        "Los informes deben pertenecer a una carga Gold local.",
    )

    execution_bytes = execution_path.read_bytes()
    validation_bytes = validation_path.read_bytes()
    execution = json.loads(execution_bytes)
    validation = json.loads(validation_bytes)
    execution_sha = hashlib.sha256(execution_bytes).hexdigest()

    require(
        execution_sha == validation["execution_report_sha256"],
        "La validación no corresponde al informe Gold.",
    )
    source_run_id = execution["gold_processing_run_id"]
    require(
        execution["scope"] == "local_gold_initial"
        and execution["status"] == "tables_verified"
        and validation["scope"] == "local_gold_model_validation"
        and validation["status"] == "passed"
        and validation["validation"]["passed"] is True
        and validation["gold_processing_run_id"] == source_run_id
        and Path(validation["execution_report_path"]).resolve()
        == execution_path,
        "La base Gold no dispone de aceptación coherente.",
    )
    source_processed_at = datetime.fromisoformat(
        execution["gold_processed_at"]
    )
    require(
        source_processed_at.tzinfo is not None
        and source_processed_at.utcoffset() is not None
        and observed_at >= source_processed_at.astimezone(timezone.utc),
        "Observación anterior a la construcción Gold o fecha inválida.",
    )
    dimensions = ("dim_product", "dim_customer")
    sources = {
        name: {
            "path": execution["tables"][name]["path"],
            "version": execution["tables"][name]["version"],
            "row_count": execution["tables"][name]["row_count"],
        }
        for name in (*dimensions, "fact_sales")
    }
    counts = {
        name: specification["row_count"]
        for name, specification in sources.items()
    }
    targets = {
        name: str(batch_root / "tables" / name)
        for name in dimensions
    }

    for name, specification in sources.items():
        accepted = execution["tables"][name]
        source_path = Path(specification["path"]).resolve()
        require(
            accepted["verified"] is True
            and type(specification["version"]) is int
            and specification["version"] == 0
            and type(specification["row_count"]) is int
            and specification["row_count"] >= 0
            and source_path
            == (execution_path.parent / "tables" / name).resolve()
            and (source_path / "_delta_log").is_dir(),
            f"Referencia Gold incompatible: {name}",
        )

    for name in dimensions:
        target = batch_root / "tables" / name
        require(
            target.resolve() == target
            and not target.exists(),
            f"Destino existente o incompatible: {name}",
        )

    report_path = batch_root / "report.json"
    report = {
        "scope": "local_scd_initialization",
        "status": "running",
        "batch_id": batch_id,
        "processing_run_id": str(uuid4()),
        "observed_at": observed_at.isoformat(),
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "execution_report_path": str(execution_path),
        "execution_report_sha256": execution_sha,
        "validation_report_path": str(validation_path),
        "source_gold_processing_run_id": source_run_id,
        "sources": sources,
        "tables": {},
        "legacy_facts_policy": "preserve_existing_dimension_keys",
        "legacy_relationships": {},
    }
    processed_at = datetime.fromisoformat(report["processed_at"])
    require(processed_at >= observed_at, "La observación está en el futuro.")

    batch_root.mkdir(parents=True, exist_ok=True)

    # Reserva exclusiva: no sustituir informes de intentos anteriores.
    with report_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    os.environ["PYSPARK_PYTHON"] = sys.executable
    spark = None
    cached = []
    try:
        builder = (
            SparkSession.builder.master("local[1]")
            .appName("arlp-m10-scd-initialization")
            .config("spark.driver.memory", "1g")
            .config("spark.sql.shuffle.partitions", "2")
            .config("spark.sql.session.timeZone", "UTC")
            .config("spark.sql.extensions",
                    "io.delta.sql.DeltaSparkSessionExtension")
            .config("spark.sql.catalog.spark_catalog",
                    "org.apache.spark.sql.delta.catalog.DeltaCatalog")
            .config("spark.databricks.delta.snapshotPartitions", "2")
        )
        spark = configure_spark_with_delta_pip(builder).getOrCreate()
        spark.sparkContext.setLogLevel("WARN")

        inputs = {}
        for name, specification in sources.items():
            frame = (
                spark.read.format("delta")
                .option("versionAsOf", specification["version"])
                .load(specification["path"])
                .cache()
            )
            cached.append(frame)
            require(frame.count() == counts[name], f"Conteo diferente: {name}")
            invalid = (
                ~F.col("gold_processing_run_id").eqNullSafe(F.lit(source_run_id))
                | ~F.col("gold_processed_at").eqNullSafe(
                    F.lit(source_processed_at.astimezone(timezone.utc))
                )
            )
            require(
                not frame.filter(invalid).limit(1).count(),
                f"Procedencia diferente: {name}",
            )
            inputs[name] = frame

        prepared = {}
        for name in dimensions:
            original = inputs[name]
            frame = initialize_scd_dimension(
                original, name, batch_id, report["processing_run_id"],
                observed_at, processed_at,
            ).cache()
            cached.append(frame)
            require(frame.count() == counts[name], f"Conteo SCD diferente: {name}")
            original_columns = frame.select(*original.columns)
            require(
                not original.exceptAll(original_columns).limit(1).count()
                and not original_columns.exceptAll(original).limit(1).count(),
                f"Se modificaron columnas originales: {name}",
            )
            key = "product_key" if name == "dim_product" else "customer_key"
            require(
                not inputs["fact_sales"].join(
                    frame.select(key), key, "left_anti"
                ).limit(1).count(),
                f"Ventas sin correspondencia en la dimensión preparada: {name}",
            )
            prepared[name] = frame

        report["status"] = "inputs_verified"
        save_report(report, report_path)

        for name, frame in prepared.items():
            result = write_verified_gold_table(
                spark, frame, targets[name]
            )
            report["tables"][name] = result
            save_report(report, report_path)
            print(f"PASS: {name}, {result['row_count']} filas persistidas.")

        for name in dimensions:
            stored = (
                spark.read.format("delta")
                .option("versionAsOf", report["tables"][name]["version"])
                .load(report["tables"][name]["path"])
            )
            key = "product_key" if name == "dim_product" else "customer_key"
            missing = inputs["fact_sales"].join(
                stored.select(key), key, "left_anti"
            ).count()
            require(missing == 0, f"Ventas huérfanas después de persistir: {name}")
            report["legacy_relationships"][name] = {
                "missing_reference_rows": missing, "passed": True,
            }
            print(f"PASS: claves heredadas de ventas conservadas en {name}.")

        report["status"] = "completed"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_report(report, report_path)
        print("PASS: inicialización SCD persistida y verificada.")
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
