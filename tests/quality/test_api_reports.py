"""Pruebas del informe y la cuarentena de API."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "quality/check_api_extraction.py"
SOURCE = ROOT / (
    "data/apis/dummyjson/products/ingestion_date=2026-10-11/"
    "run_id=172c6634-a566-4ae8-bfc7-04ae228dae77"
)
PAGE = "category=laptops/page_000001.json"


class ApiReportTests(unittest.TestCase):
    def copy_source(self, root):
        destination = root / SOURCE.parent.name / SOURCE.name
        shutil.copytree(SOURCE, destination)
        return destination

    def execute(self, source, output, expected_exit):
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--run-dir", str(source),
                "--output-dir", str(output),
            ],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(
            result.returncode, expected_exit, result.stdout + result.stderr
        )
        return json.loads((output / "report.json").read_text(encoding="utf-8"))

    def test_rejected_product_preserves_response_and_pointer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.copy_source(root)
            path = source / PAGE
            data = json.loads(path.read_bytes())
            data["products"][0]["stock"] = -1
            payload = (json.dumps(data) + "\n").encode("utf-8")
            path.write_bytes(payload)

            # Actualiza la integridad de la copia de prueba para que
            # el rechazo se deba al stock y no al transporte.
            digest = hashlib.sha256(payload).hexdigest()
            sidecar = source / (PAGE + ".metadata.json")
            provenance = json.loads(sidecar.read_bytes())
            provenance["payload_sha256"] = digest
            provenance["size_bytes"] = len(payload)
            sidecar_payload = (
                json.dumps(provenance) + "\n"
            ).encode("utf-8")
            sidecar.write_bytes(sidecar_payload)

            manifest_path = source / "manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            manifest["files"][PAGE].update({
                "sha256": digest,
                "size_bytes": len(payload),
            })
            manifest["files"][PAGE + ".metadata.json"].update({
                "sha256": hashlib.sha256(sidecar_payload).hexdigest(),
                "size_bytes": len(sidecar_payload),
            })
            manifest_path.write_text(
                json.dumps(manifest) + "\n", encoding="utf-8"
            )

            output = root / "output"
            report = self.execute(source, output, 0)
            self.assertEqual(report["status"], "completed_for_scope")
            self.assertEqual(
                report["records"],
                {"read": 38, "accepted": 37, "rejected": 1},
            )
            self.assertEqual(report["manifest_controls"], "not_fully_validated")
            self.assertEqual(len(report["quarantine_files"]), 1)

            entry = report["quarantine_files"][0]
            parquet = output / entry["path"]
            content = parquet.read_bytes()
            self.assertEqual(entry["size_bytes"], len(content))
            self.assertEqual(
                entry["sha256"], hashlib.sha256(content).hexdigest()
            )
            rows = pq.ParquetFile(parquet).read().to_pylist()
            self.assertEqual(len(rows), 1)
            self.assertEqual(entry["row_count"], 1)
            row = rows[0]
            self.assertEqual(row["raw_response"], payload.decode("utf-8"))
            self.assertEqual(row["record_pointer"], "/products/0")
            self.assertEqual(row["source_sha256"], digest)
            self.assertEqual(
                row["processing_run_id"], report["processing_run_id"]
            )
            self.assertEqual(
                row["ingestion_run_id"], manifest["ingestion_run_id"]
            )
            self.assertIn(
                "stock", {error["field"] for error in row["errors"]}
            )

    def test_bad_hash_blocks_without_quarantine(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self.copy_source(root)
            path = source / PAGE
            path.write_bytes(path.read_bytes() + b"\n")

            output = root / "output"
            report = self.execute(source, output, 1)
            self.assertEqual(report["status"], "blocked")
            self.assertIsNone(report["records_processed"])
            self.assertIsNone(report["records"])
            self.assertEqual(report["quarantine_files"], [])
            self.assertEqual(list(output.glob("*.parquet")), [])
            self.assertIn(
                "DQ002", {error["code"] for error in report["errors"]}
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
