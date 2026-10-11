"""Publica una extracción local validada de API en Bronze."""

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import date
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingestion/synthetic"))

from ingest_batches import upload, verify
from api_common import require, utc_now, write_json


def prepare(run_dir, api_root, staged):
    manifest_bytes = (run_dir / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest.get("schema_version") == 1, "Versión incompatible")
    require(manifest.get("status") == "completed", "Extracción incompleta")

    source = manifest.get("source_system")
    require(source in {"dummyjson", "bcrpdata"}, "Fuente no admitida")
    run_id = manifest["ingestion_run_id"]
    UUID(run_id)
    ingestion_date = date.fromisoformat(manifest["ingestion_date"]).isoformat()

    if source == "dummyjson":
        expected = (
            f"dummyjson/products/ingestion_date={ingestion_date}/"
            f"run_id={run_id}"
        )
    else:
        require(manifest.get("series_code") == "PD04638PD", "Serie incorrecta")
        expected = (
            "bcrpdata/exchange_rates/series_code=pd04638pd/"
            f"ingestion_date={ingestion_date}/run_id={run_id}"
        )

    require(
        run_dir == (api_root / expected).resolve(),
        "La ruta no coincide con la identidad del manifiesto",
    )

    files = manifest.get("files")
    require(isinstance(files, dict) and bool(files), "Inventario inválido")
    require("manifest.json" not in files, "Inventario incluye el manifiesto")

    actual = {
        path.relative_to(run_dir).as_posix()
        for path in run_dir.rglob("*") if path.is_file()
    }
    require(
        actual == set(files) | {"manifest.json"},
        "Archivos ausentes o adicionales",
    )

    inventory = {}
    for relative, metadata in files.items():
        path = (run_dir / relative).resolve()
        require(path.is_relative_to(run_dir), f"Ruta no segura: {relative}")
        require(isinstance(metadata, dict), f"Metadatos inválidos: {relative}")
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        require(digest == metadata.get("sha256"), f"Hash diferente: {relative}")
        require(
            len(payload) == metadata.get("size_bytes"),
            f"Tamaño diferente: {relative}",
        )
        target = staged / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        inventory[relative] = {"sha256": digest, "size_bytes": len(payload)}

    (staged / "manifest.json").write_bytes(manifest_bytes)
    inventory["manifest.json"] = {
        "sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "size_bytes": len(manifest_bytes),
    }
    return manifest, expected, inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--api-root", type=Path, default=ROOT / "data/apis")
    parser.add_argument("--account-name", default="starlpdevdiego01")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    if args.publish and args.report is None:
        parser.error("--publish requiere --report.")
    if args.publish:
        require(not args.report.exists(), "El informe ya existe")

    with tempfile.TemporaryDirectory() as temporary:
        staged = Path(temporary) / "staged"
        staged.mkdir()
        manifest, prefix, inventory = prepare(
            args.run_dir.resolve(), args.api_root.resolve(), staged,
        )

        print(f"PASS: {len(inventory)} archivos preparados, incluido el manifiesto.")
        print(f"DESTINO: bronze/{prefix}/")
        if not args.publish:
            print("ALCANCE: preparación local; no se publicaron archivos.")
            return

        report = {
            "schema_version": 1,
            "source_system": manifest["source_system"],
            "ingestion_run_id": manifest["ingestion_run_id"],
            "account_name": args.account_name,
            "container": "bronze",
            "prefix": prefix,
            "publication_started_at": utc_now(),
            "publication_finished_at": None,
            "status": "in_progress",
            "files": {},
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.report, report)

        def save():
            args.report.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        filenames = sorted(set(inventory) - {"manifest.json"})
        filenames.append("manifest.json")

        try:
            for index, relative in enumerate(filenames):
                name = f"{prefix}/{relative}"
                entry = {
                    **inventory[relative],
                    "blob_name": name,
                    "status": "uploading",
                }
                report["files"][relative] = entry
                save()

                upload(args.account_name, name, staged / relative)
                entry["status"] = "uploaded"
                save()

                verify(
                    args.account_name, name, entry["sha256"],
                    Path(temporary) / f"verification_{index:04d}",
                )
                entry["status"] = "verified"
                save()
                print(f"PASS: {relative}, publicado y verificado.")

            report["status"] = "completed"
        except BaseException:
            report["status"] = "failed"
            raise
        finally:
            report["publication_finished_at"] = utc_now()
            save()
            print(f"INFORME: {args.report}")

    print("COMPLETADO: extracción publicada y verificada en Bronze.")


if __name__ == "__main__":
    main()
