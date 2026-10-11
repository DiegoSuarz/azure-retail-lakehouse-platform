"""Publica los lotes funcionales originales en Bronze."""

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from validate_batches import BATCHES, require, validate_batch


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def az(*arguments):
    subprocess.run(
        ["az", *arguments, "--only-show-errors", "--output", "none"],
        check=True,
    )


def upload(account, name, path):
    content_types = {
        ".csv": "text/csv",
        ".jsonl": "application/x-ndjson",
        ".json": "application/json",
    }
    az(
        "storage", "blob", "upload",
        "--account-name", account,
        "--container-name", "bronze",
        "--name", name,
        "--file", str(path),
        "--auth-mode", "login",
        "--type", "block",
        "--content-type", content_types[path.suffix],
        "--overwrite", "false",
        "--if-none-match", "*",
    )


def verify(account, name, expected_sha256, destination):
    az(
        "storage", "blob", "download",
        "--account-name", account,
        "--container-name", "bronze",
        "--name", name,
        "--file", str(destination),
        "--auth-mode", "login",
    )
    actual = hashlib.sha256(destination.read_bytes()).hexdigest()
    require(actual == expected_sha256, f"Hash cloud diferente: {name}")


def save_report(path, report):
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir", type=Path,
        default=Path("data/incremental/functional"),
    )
    parser.add_argument("--account-name", default="starlpdevdiego01")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    if args.publish and args.report is None:
        parser.error("--publish requiere --report.")
    if args.publish:
        require(shutil.which("az") is not None, "Azure CLI no disponible")
        require(not args.report.exists(), "El informe ya existe")

    run_id = str(uuid4())
    report = {
        "schema_version": 1,
        "ingestion_run_id": run_id,
        "account_name": args.account_name,
        "container": "bronze",
        "started_at": now(),
        "finished_at": None,
        "status": "prepared",
        "batches": {},
    }

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        manifests = {}

        for batch_id in BATCHES:
            source = args.source_dir / batch_id
            require(source.is_dir(), f"Lote ausente: {batch_id}")
            original = validate_batch(source)
            staged = root / batch_id
            staged.mkdir()

            for filename in [*original["files"], "manifest.json"]:
                shutil.copyfile(source / filename, staged / filename)

            manifests[batch_id] = validate_batch(staged)
            require(
                manifests[batch_id] == original,
                f"El manifiesto cambió durante la preparación: {batch_id}",
            )
            prefix = (
                f"synthetic/incremental/batch_id={batch_id}/"
                f"run_id={run_id}"
            )
            report["batches"][batch_id] = {
                "prefix": prefix,
                "status": "pending",
                "files": {},
            }
            print(f"DESTINO: bronze/{prefix}/")

        print(f"INGESTION_RUN_ID: {run_id}")

        if not args.publish:
            print("PASS: preparación validada; no se publicaron archivos.")
            return

        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")

        report["status"] = "in_progress"
        try:
            for batch_id in BATCHES:
                staged = root / batch_id
                manifest = manifests[batch_id]
                batch = report["batches"][batch_id]
                batch["status"] = "in_progress"

                filenames = [*manifest["files"], "manifest.json"]
                for filename in filenames:
                    path = staged / filename
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    name = f"{batch['prefix']}/{filename}"
                    entry = {
                        "blob_name": name,
                        "sha256": digest,
                        "size_bytes": path.stat().st_size,
                        "status": "uploading",
                    }
                    batch["files"][filename] = entry
                    save_report(args.report, report)

                    upload(args.account_name, name, path)
                    entry["status"] = "uploaded"
                    save_report(args.report, report)

                    verify(
                        args.account_name, name, digest,
                        staged / f"downloaded_{filename}",
                    )
                    entry["status"] = "verified"
                    save_report(args.report, report)
                    print(f"PASS: {batch_id}/{filename}, publicado y verificado.")

                batch["status"] = "completed"
                save_report(args.report, report)

            report["status"] = "completed"
        except BaseException:
            report["status"] = "failed"
            raise
        finally:
            report["finished_at"] = now()
            save_report(args.report, report)
            print(f"INFORME: {args.report}")

    print("COMPLETADO: cuatro lotes publicados y verificados en Bronze.")


if __name__ == "__main__":
    main()
