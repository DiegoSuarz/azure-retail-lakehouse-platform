"""Pruebas de integridad y clasificación de evidencias."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "quality/prepare_publication.py"
SOURCE = ROOT / "data/validation/quality_s19"


class PublicationPreparationTests(unittest.TestCase):
    def execute(self, report, output):
        return subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--reports", str(report),
                "--output-dir", str(output),
            ],
            cwd=ROOT, capture_output=True, text=True,
        )

    def test_valid_evidence_preserves_bytes_and_routes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "inputs"
            shutil.copytree(SOURCE, source)
            output = root / "publication"
            result = self.execute(source / "report.json", output)
            self.assertEqual(
                result.returncode, 0, result.stdout + result.stderr
            )
            plan = json.loads(
                (output / "publication_plan.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(plan["files"]), 3)
            self.assertEqual(
                sum(entry["container"] == "quarantine" for entry in plan["files"]),
                2,
            )
            for entry in plan["files"]:
                payload = (output / entry["local_path"]).read_bytes()
                filename = Path(entry["blob_name"]).name
                self.assertEqual(payload, (source / filename).read_bytes())
                self.assertEqual(len(payload), entry["size_bytes"])
                self.assertEqual(
                    hashlib.sha256(payload).hexdigest(), entry["sha256"]
                )

    def test_altered_evidence_is_rejected(self):
        for defect in ("hash", "classification"):
            with self.subTest(defect=defect):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    source = root / "inputs"
                    shutil.copytree(SOURCE, source)
                    report_path = source / "report.json"
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    entry = report["quarantine_files"][0]
                    path = source / entry["path"]

                    if defect == "hash":
                        path.write_bytes(path.read_bytes() + b"\n")
                    else:
                        table = pq.ParquetFile(path).read()
                        rows = table.to_pylist()
                        rows[0]["status"] = "accepted"
                        pq.write_table(
                            pa.Table.from_pylist(rows, schema=table.schema),
                            path, compression="snappy",
                        )
                        payload = path.read_bytes()
                        entry["sha256"] = hashlib.sha256(payload).hexdigest()
                        entry["size_bytes"] = len(payload)
                        report_path.write_text(
                            json.dumps(report) + "\n", encoding="utf-8"
                        )

                    output = root / "publication"
                    result = self.execute(report_path, output)
                    self.assertNotEqual(result.returncode, 0)
                    expected = (
                        "Hash diferente" if defect == "hash"
                        else "Identidad o clasificación incompatible"
                    )
                    self.assertIn(expected, result.stdout + result.stderr)
                    self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
