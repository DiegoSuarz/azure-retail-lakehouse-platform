"""Prepara evidencias verificadas de calidad para su publicación."""

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from uuid import UUID

import pyarrow.parquet as pq


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def prepare(report_paths, output):
    entries = []
    run_ids = set()
    destinations = set()

    def stage(payload, container, blob_name):
        destination = (container, blob_name)
        require(destination not in destinations, "Destino repetido")
        destinations.add(destination)
        relative = f"files/{len(entries):04d}"
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        entries.append({
            "local_path": relative,
            "container": container,
            "blob_name": blob_name,
            "size_bytes": len(payload),
            "sha256": digest(payload),
        })

    for report_path in report_paths:
        report_path = report_path.resolve()
        report_payload = report_path.read_bytes()
        report = json.loads(report_payload)
        require(
            type(report.get("schema_version")) is int
            and report["schema_version"] == 1,
            f"Versión incompatible: {report_path}",
        )
        run_id = report.get("processing_run_id")
        require(isinstance(run_id, str), "processing_run_id ausente")
        UUID(run_id)
        require(run_id not in run_ids, "processing_run_id repetido")
        run_ids.add(run_id)
        require(
            report.get("status") in {"completed_for_scope", "validated", "blocked"},
            f"Estado de informe incompatible: {report_path}",
        )

        declared = set()
        for field, allowed_statuses in (
            ("quarantine_files", {"rejected", "conflict"}),
            ("pending_files", {"pending"}),
        ):
            files = report.get(field, [])
            require(isinstance(files, list), f"Inventario incompatible: {field}")
            for metadata in files:
                require(isinstance(metadata, dict), "Entrada de inventario inválida")
                filename = metadata.get("path")
                require(
                    isinstance(filename, str)
                    and Path(filename).name == filename
                    and filename.endswith(".parquet"),
                    "Nombre de Parquet incompatible",
                )
                require(filename not in declared, "Archivo declarado dos veces")
                declared.add(filename)
                path = report_path.parent / filename
                require(
                    path.is_file() and not path.is_symlink(),
                    f"Archivo ausente o enlace: {path}",
                )
                payload = path.read_bytes()
                require(digest(payload) == metadata.get("sha256"), f"Hash diferente: {path}")
                require(
                    type(metadata.get("size_bytes")) is int
                    and len(payload) == metadata["size_bytes"],
                    f"Tamaño diferente: {path}",
                )
                rows = pq.ParquetFile(path).read().to_pylist()
                require(
                    type(metadata.get("row_count")) is int
                    and len(rows) == metadata["row_count"] and bool(rows),
                    f"Conteo diferente o archivo vacío: {path}",
                )
                require(
                    all(
                        row.get("processing_run_id") == run_id
                        and row.get("ingestion_run_id") == report.get("ingestion_run_id")
                        and row.get("status") in allowed_statuses
                        for row in rows
                    ),
                    f"Identidad o clasificación incompatible: {path}",
                )
                sources = {row.get("source_system") for row in rows}
                entities = {row.get("entity") for row in rows}
                require(
                    len(sources) == len(entities) == 1,
                    "El archivo mezcla fuentes o entidades; requiere separación previa",
                )
                source = next(iter(sources))
                entity = next(iter(entities))
                require(
                    all(
                        isinstance(value, str)
                        and re.fullmatch(r"[a-z][a-z0-9_]*", value)
                        for value in (source, entity)
                    ),
                    "Fuente o entidad incompatible con la ruta",
                )
                require(
                    report.get("source_system") == source,
                    f"Fuente diferente del informe: {path}",
                )
                if field == "quarantine_files":
                    container = "quarantine"
                    prefix = f"source={source}/entity={entity}/run_id={run_id}"
                else:
                    container = "operations"
                    prefix = f"pending_events/run_id={run_id}"
                stage(payload, container, f"{prefix}/{filename}")

        if declared:
            actual = {path.name for path in report_path.parent.glob("*.parquet")}
            require(actual == declared, f"Parquet adicionales: {report_path.parent}")

        stage(
            report_payload, "operations",
            f"quality/run_id={run_id}/report.json",
        )

    return {
        "schema_version": 1,
        "status": "prepared",
        "processing_run_ids": sorted(run_ids),
        "files": entries,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, nargs="+", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    output = args.output_dir.resolve()
    if output.exists():
        parser.error("La carpeta de preparación ya existe.")
    for report in args.reports:
        if output.is_relative_to(report.resolve().parent):
            parser.error("La preparación debe estar fuera de las carpetas de informes.")

    output.mkdir(parents=True, exist_ok=False)
    try:
        plan = prepare(args.reports, output)
        with (output / "publication_plan.json").open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except Exception:
        shutil.rmtree(output)
        raise

    for entry in plan["files"]:
        print(f"DESTINO: {entry['container']}/{entry['blob_name']}")
    print(f"PASS: {len(plan['files'])} archivos preparados y verificados.")
    print(f"PLAN: {output / 'publication_plan.json'}")


if __name__ == "__main__":
    main()
