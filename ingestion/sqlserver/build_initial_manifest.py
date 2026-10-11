"""Genera el manifiesto local después de validar la extracción inicial."""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
TABLES = {"categories", "products", "customers", "orders", "order_items"}


def require(condition, message):
    if not condition:
        raise SystemExit(f"FAIL: {message}")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def identifier(value, label):
    require(isinstance(value, str), f"Falta {label}")
    try:
        UUID(value)
    except ValueError:
        raise SystemExit(f"FAIL: UUID inválido en {label}")
    return value


def utc_date(value, label):
    require(isinstance(value, str), f"Falta {label}")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit(f"FAIL: Fecha inválida en {label}")
    require(result.tzinfo is not None and result.utcoffset() == timedelta(0),
            f"{label} debe estar en UTC")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--parquet-dir", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    args = parser.parse_args()

    metadata = read_json(args.metadata)
    require(metadata["schema_version"] == 1, "Versión de metadatos")
    require(metadata["pipeline_name"] == "pl_ingest_sqlserver_initial",
            "Pipeline inesperado")
    run_id = identifier(metadata["ingestion_run_id"], "ingestion_run_id")
    require(metadata["pipeline_status"] == "Succeeded", "Pipeline no exitoso")
    require(metadata["no_source_writes_confirmed"] is True,
            "Ventana sin escrituras no confirmada")
    require(set(metadata["entities"]) == TABLES, "Entidades de ADF incompletas")

    started = utc_date(metadata["extraction_started_at"], "inicio de extracción")
    finished = utc_date(metadata["extraction_finished_at"], "fin de extracción")
    require(started <= finished, "Fechas de extracción invertidas")
    require(args.parquet_dir.name == f"run_id={run_id}",
            "La carpeta descargada debe llamarse run_id=<RunId>")

    output = args.parquet_dir / "manifest.json"
    require(not output.exists(), "El manifiesto ya existe; no se sobrescribirá")

    before = read_json(args.before)
    after = read_json(args.after)
    before_finished = utc_date(
        before["capture_finished_at"], "fin de captura inicial"
    )
    after_started = utc_date(
        after["capture_started_at"], "inicio de captura posterior"
    )
    require(before_finished <= started <= finished <= after_started,
            "Las capturas no delimitan la extracción")

    for name, metrics in metadata["entities"].items():
        identifier(metrics["activity_run_id"], f"activity_run_id/{name}")
        require(metrics["status"] == "Succeeded", f"Copia no exitosa: {name}")
        require(metrics["consistency_verification"] == "Verified",
                f"Consistencia no verificada por Copy: {name}")
        for field in ("rows_read", "rows_copied", "files_written"):
            value = metrics[field]
            require(type(value) is int and value >= 0,
                    f"Métrica incompleta o inválida: {name}/{field}")

    with tempfile.TemporaryDirectory() as temporary:
        report_path = Path(temporary) / "validation.json"
        result = subprocess.run([
            sys.executable,
            str(ROOT / "tests/ingestion/validate_initial_parquet.py"),
            "--before", str(args.before.resolve()),
            "--after", str(args.after.resolve()),
            "--parquet-dir", str(args.parquet_dir.resolve()),
            "--report", str(report_path),
        ], check=False)
        require(result.returncode == 0, "Validación de Parquet fallida")
        report = read_json(report_path)

    require(report["status"] == "validated", "Informe no validado")
    entities = report["entities"]
    for name, entity in entities.items():
        metrics = metadata["entities"][name]
        require(metrics["rows_read"] == entity["source_row_count"],
                f"Filas leídas diferentes del origen: {name}")
        require(metrics["rows_copied"] == entity["destination_row_count"],
                f"Filas copiadas diferentes del destino: {name}")
        require(metrics["files_written"] == len(entity["files"]),
                f"Cantidad de archivos diferente: {name}")
        entity.update({
            "copy_rows_read": metrics["rows_read"],
            "copy_rows_copied": metrics["rows_copied"],
            "copy_activity_run_id": metrics["activity_run_id"],
            "copy_consistency_verification": metrics["consistency_verification"],
        })

    manifest = {
        "schema_version": 1,
        "ingestion_run_id": run_id,
        "source_system": "sqlserver",
        "source_database": "TechRetail_OLTP",
        "pipeline_name": metadata["pipeline_name"],
        "synthetic_cutoff_exclusive": "2026-10-01T00:00:00.000Z",
        "extraction_started_at": metadata["extraction_started_at"],
        "extraction_finished_at": metadata["extraction_finished_at"],
        "validated_at": report["validated_at"],
        "consistency": {
            "method": "no_writes_window_with_before_after_comparison",
            "no_source_writes_confirmed": True,
            "source_before_sha256": report["source_before_sha256"],
            "source_after_sha256": report["source_after_sha256"],
            "limitation": "Las capturas no detectan cambios transitorios revertidos.",
        },
        "entities": entities,
        "reference_controls": report["reference_controls"],
        "reconciliation": report["reconciliation"],
        "status": "completed",
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"GENERADO: {output}")
    print("ALCANCE: manifiesto local; verificación cloud y publicación pendientes.")


if __name__ == "__main__":
    main()
