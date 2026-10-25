"""Publica la base y los lotes de prueba CDC de productos en Bronze."""

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ingestion/synthetic"))

from ingest_batches import upload, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--account-name", default="starlpdevdiego01")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    names = ("baseline.json", "batch_001.json", "batch_002.json")
    payloads = {
        name: (args.source_root / name).read_bytes()
        for name in names
    }
    documents = {
        name: json.loads(payload)
        for name, payload in payloads.items()
    }

    for name, document in documents.items():
        if (
            document.get("source_database") != "TechRetail_OLTP"
            or document.get("capture_instance") != "dbo_products"
        ):
            raise ValueError(f"Origen incompatible: {name}")

    baseline = documents["baseline.json"]
    first = documents["batch_001.json"]
    second = documents["batch_002.json"]

    if first["after_lsn"] != baseline["baseline_lsn"]:
        raise ValueError("El primer lote no continúa desde la base.")
    if second["after_lsn"] != first["to_lsn"]:
        raise ValueError("El segundo lote no continúa desde el primero.")

    identity = hashlib.sha256()
    for name in names:
        identity.update(name.encode("utf-8"))
        identity.update(hashlib.sha256(payloads[name]).digest())

    run_id = str(uuid5(NAMESPACE_URL, "arlp:products-cdc:" + identity.hexdigest()))
    prefix = f"sqlserver/techretail_oltp/cdc/products/run_id={run_id}"
    cloud_root = (
        f"abfss://bronze@{args.account_name}.dfs.core.windows.net/{prefix}"
    )

    print("INGESTION RUN ID:", run_id)
    print("DESTINO:", cloud_root)
    print("PRODUCTOS BASE:", len(baseline["products"]))
    print("EVENTOS:", len(first["changes"]), "+", len(second["changes"]))

    if not args.publish:
        print("PREPARACIÓN: no se publicaron archivos.")
        return

    with tempfile.TemporaryDirectory() as folder:
        temporary = Path(folder)
        for index, name in enumerate(names):
            staged = temporary / name
            staged.write_bytes(payloads[name])
            digest = hashlib.sha256(payloads[name]).hexdigest()

            upload(args.account_name, f"{prefix}/{name}", staged)
            verify(
                args.account_name,
                f"{prefix}/{name}",
                digest,
                temporary / f"download_{index}.json",
            )
            print(f"PASS: {name}, publicado y verificado.")

    print("PASS: tres archivos conservados en Bronze.")


if __name__ == "__main__":
    main()
