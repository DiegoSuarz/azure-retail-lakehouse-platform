"""Publica una extracción local validada de API en Bronze."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingestion/synthetic"))

from ingest_batches import upload, verify
from api_common import require, utc_now, write_json

sys.path.insert(0, str(ROOT))
from quality.api_extraction_input import read_extraction
from quality.dummyjson_rules import evaluate_dummyjson
from quality.bcrpdata_rules import evaluate_bcrpdata


def prepare(run_dir, api_root, staged):
    extraction, responses, payloads = read_extraction(run_dir)
    evaluator = (
        evaluate_dummyjson
        if extraction["source_system"] == "dummyjson"
        else evaluate_bcrpdata
    )
    records = evaluator(extraction, responses, payloads)
    require(
        bool(records) and all(row["status"] == "accepted" for row in records),
        "La extracción contiene registros inválidos o está vacía",
    )

    source = extraction["source_system"]
    run_id = extraction["ingestion_run_id"]
    ingestion_date = extraction["ingestion_date"]
    if source == "dummyjson":
        expected = (
            f"dummyjson/products/ingestion_date={ingestion_date}/"
            f"run_id={run_id}"
        )
    else:
        expected = (
            "bcrpdata/exchange_rates/series_code=pd04638pd/"
            f"ingestion_date={ingestion_date}/run_id={run_id}"
        )
    require(
        run_dir == (api_root / expected).resolve(),
        "La ruta no coincide con la identidad de extracción",
    )

    inventory = {}
    for relative, payload in payloads.items():
        target = staged / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        inventory[relative] = {
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }
    return extraction, expected, inventory


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
        extraction, prefix, inventory = prepare(
            args.run_dir.resolve(), args.api_root.resolve(), staged,
        )

        print(f"PASS: {len(inventory)} archivos de respuestas y metadatos preparados.")
        print(f"DESTINO: bronze/{prefix}/")
        if not args.publish:
            print("ALCANCE: preparación local; no se publicaron archivos.")
            return

        report = {
            "schema_version": 1,
            "source_system": extraction["source_system"],
            "ingestion_run_id": extraction["ingestion_run_id"],
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

        filenames = sorted(inventory)

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
