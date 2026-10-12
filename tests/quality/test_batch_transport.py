"""Comprueba el bloqueo de lotes con defectos de transporte."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "quality/validate_batch_transport.py"
SOURCE = ROOT / "data/incremental/functional/batch_001"


class BatchTransportTests(unittest.TestCase):
    def test_defective_batches_are_blocked(self):
        cases = (
            ("invalid_manifest", "DQ001"),
            ("missing_file", "DQ002"),
            ("incorrect_count", "DQ003"),
            ("incorrect_header", "DQ004"),
        )

        for defect, expected_code in cases:
            with self.subTest(defect=defect):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    batch = root / "batch"
                    shutil.copytree(SOURCE, batch)
                    manifest_path = batch / "manifest.json"
                    manifest = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )

                    if defect == "invalid_manifest":
                        manifest["schema_version"] = 999
                    elif defect == "missing_file":
                        (batch / "orders.csv").unlink()
                    elif defect == "incorrect_count":
                        manifest["files"]["orders.csv"]["row_count"] += 1
                    else:
                        path = batch / "orders.csv"
                        payload = path.read_bytes()
                        header, separator, records = payload.partition(b"\n")
                        self.assertTrue(separator)
                        header = header.replace(
                            b"order_id", b"unexpected_id", 1
                        )
                        payload = header + separator + records
                        path.write_bytes(payload)

                        # Hash correcto para aislar el defecto de estructura.
                        metadata = manifest["files"]["orders.csv"]
                        metadata["sha256"] = hashlib.sha256(payload).hexdigest()
                        if "size_bytes" in metadata:
                            metadata["size_bytes"] = len(payload)

                    manifest_path.write_text(
                        json.dumps(manifest) + "\n", encoding="utf-8"
                    )

                    before = {
                        path.relative_to(batch): path.read_bytes()
                        for path in batch.rglob("*") if path.is_file()
                    }
                    report_path = root / "report.json"
                    result = subprocess.run(
                        [
                            sys.executable, str(SCRIPT),
                            "--batch-dir", str(batch),
                            "--report", str(report_path),
                        ],
                        cwd=ROOT, capture_output=True, text=True,
                    )

                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertTrue(
                        report_path.is_file(), result.stdout + result.stderr
                    )
                    report = json.loads(
                        report_path.read_text(encoding="utf-8")
                    )
                    self.assertEqual(report["status"], "blocked")
                    self.assertIsNone(report["records_processed"])
                    self.assertFalse(report["business_rules_evaluated"])
                    self.assertIn(
                        expected_code,
                        {error["code"] for error in report["errors"]},
                    )

                    after = {
                        path.relative_to(batch): path.read_bytes()
                        for path in batch.rglob("*") if path.is_file()
                    }
                    self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
