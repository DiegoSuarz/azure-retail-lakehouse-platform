"""Publica un paquete de evidencias de calidad y verifica sus archivos."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def validate_package(root):
    plan_bytes = (root / "publication_plan.json").read_bytes()
    plan = json.loads(plan_bytes)
    require(
        type(plan.get("schema_version")) is int
        and plan["schema_version"] == 1
        and plan.get("status") == "prepared",
        "Plan incompatible",
    )
    files = plan.get("files")
    require(isinstance(files, list) and bool(files), "Inventario vacío")
    snapshots = []
    destinations = set()
    local_paths = set()
    run_ids = set()

    patterns = {
        "operations": (
            r"(?:quality/run_id=([^/]+)/report\.json"
            r"|pending_events/run_id=([^/]+)/[a-z][a-z0-9_]*\.parquet)"
        ),
        "quarantine": (
            r"source=[a-z][a-z0-9_]*/entity=[a-z][a-z0-9_]*/"
            r"run_id=([^/]+)/[a-z][a-z0-9_]*\.parquet"
        ),
    }

    for entry in files:
        require(isinstance(entry, dict), "Entrada de inventario incompatible")
        container = entry.get("container")
        require(
            isinstance(container, str) and container in patterns,
            "Contenedor incompatible",
        )
        name = entry.get("blob_name")
        require(isinstance(name, str), "Nombre de destino ausente")
        match = re.fullmatch(patterns[container], name)
        require(match is not None, f"Ruta de destino incompatible: {name}")
        run_id = next(value for value in match.groups() if value is not None)
        UUID(run_id)
        run_ids.add(run_id)

        destination = (container, name)
        require(destination not in destinations, "Destino repetido")
        destinations.add(destination)

        relative = entry.get("local_path")
        require(
            isinstance(relative, str)
            and re.fullmatch(r"files/[0-9]{4,}", relative),
            "Ruta local incompatible",
        )
        require(relative not in local_paths, "Archivo local repetido")
        local_paths.add(relative)
        path = root / relative
        require(
            path.is_file() and not path.is_symlink()
            and path.resolve().is_relative_to(root),
            f"Archivo ausente o ruta incompatible: {relative}",
        )
        payload = path.read_bytes()
        require(
            hashlib.sha256(payload).hexdigest() == entry.get("sha256"),
            f"Hash diferente: {relative}",
        )
        require(
            type(entry.get("size_bytes")) is int
            and len(payload) == entry["size_bytes"],
            f"Tamaño diferente: {relative}",
        )
        snapshots.append((dict(entry), payload))

    declared_runs = plan.get("processing_run_ids")
    require(
        isinstance(declared_runs, list)
        and len(declared_runs) == len(run_ids)
        and set(declared_runs) == run_ids,
        "Identificadores diferentes del inventario",
    )
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*") if path.is_file()
    }
    require(
        actual == local_paths | {"publication_plan.json"},
        "Archivos ausentes o adicionales en el paquete",
    )

    # Los informes se publican después de todas las evidencias.
    snapshots.sort(key=lambda item: item[0]["blob_name"].endswith(".json"))
    return hashlib.sha256(plan_bytes).hexdigest(), snapshots


def az(*arguments):
    subprocess.run(
        ["az", *arguments, "--only-show-errors", "--output", "none"],
        check=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--account-name", default="starlpdevdiego01")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    root = args.package_dir.resolve()
    if args.publish:
        if args.report is None:
            parser.error("--publish requiere --report.")
        if args.report.exists() or args.report.resolve().is_relative_to(root):
            parser.error("El informe debe ser nuevo y estar fuera del paquete.")

    plan_hash, snapshots = validate_package(root)
    for entry, _ in snapshots:
        print(f"DESTINO: {entry['container']}/{entry['blob_name']}")
    print(f"PASS: {len(snapshots)} archivos verificados antes de publicar.")

    if not args.publish:
        print("ALCANCE: revisión local del paquete.")
        return

    report = {
        "schema_version": 1,
        "account_name": args.account_name,
        "publication_plan_sha256": plan_hash,
        "started_at": now(),
        "finished_at": None,
        "status": "in_progress",
        "files": [],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    def save():
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    try:
        with tempfile.TemporaryDirectory() as temporary:
            staged_root = Path(temporary)
            for index, (entry, payload) in enumerate(snapshots):
                staged = staged_root / f"source_{index}"
                downloaded = staged_root / f"download_{index}"
                staged.write_bytes(payload)
                progress = {**entry, "status": "uploading"}
                report["files"].append(progress)
                save()

                az(
                    "storage", "blob", "upload",
                    "--account-name", args.account_name,
                    "--container-name", entry["container"],
                    "--name", entry["blob_name"],
                    "--file", str(staged),
                    "--auth-mode", "login",
                    "--type", "block",
                    "--content-type", (
                        "application/json"
                        if entry["blob_name"].endswith(".json")
                        else "application/octet-stream"
                    ),
                    "--overwrite", "false",
                    "--if-none-match", "*",
                )
                progress["status"] = "uploaded"
                save()

                az(
                    "storage", "blob", "download",
                    "--account-name", args.account_name,
                    "--container-name", entry["container"],
                    "--name", entry["blob_name"],
                    "--file", str(downloaded),
                    "--auth-mode", "login",
                )
                downloaded_payload = downloaded.read_bytes()
                require(
                    len(downloaded_payload) == entry["size_bytes"]
                    and hashlib.sha256(downloaded_payload).hexdigest()
                    == entry["sha256"],
                    f"Contenido cloud diferente: {entry['blob_name']}",
                )
                progress["status"] = "verified"
                save()
                print(f"PASS: publicado y verificado: {entry['blob_name']}")

        report["status"] = "completed"
    except BaseException:
        report["status"] = "failed"
        raise
    finally:
        report["finished_at"] = now()
        save()
        print(f"INFORME: {args.report}")


if __name__ == "__main__":
    main()
