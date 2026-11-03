"""Comprueba el bloqueo de lotes con defectos de transporte."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "quality/validate_batch_transport.py"
sys.path.insert(0, str(ROOT / "quality"))
from validate_batch_transport import HEADERS


class BatchTransportTests(unittest.TestCase):
    def test_defective_batches_are_blocked(self):
        cases = (
            ("incorrect_identity", "DQ001"),
            ("missing_file", "DQ002"),
            ("additional_file", "DQ002"),
            ("malformed_jsonl", "DQ004"),
            ("incorrect_header", "DQ004"),
        )

        for defect, expected_code in cases:
            with self.subTest(defect=defect):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    batch = root / "batch"
                    batch.mkdir()
                    for filename, fields in HEADERS.items():
                        (batch / filename).write_text(
                            ",".join(fields) + "\n", encoding="utf-8"
                        )
                    (batch / "changes.jsonl").write_text(
                        "{}\n", encoding="utf-8"
                    )

                    if defect == "missing_file":
                        (batch / "orders.csv").unlink()
                    elif defect == "additional_file":
                        (batch / "unexpected.txt").write_text("extra")
                    elif defect == "malformed_jsonl":
                        (batch / "changes.jsonl").write_text(
                            '{"event_id":\n', encoding="utf-8"
                        )
                    elif defect == "incorrect_header":
                        path = batch / "orders.csv"
                        path.write_text(
                            path.read_text(encoding="utf-8").replace(
                                "order_id", "unexpected_id", 1
                            ),
                            encoding="utf-8",
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
                            "--expected-batch-id",
                            "different" if defect == "incorrect_identity" else "batch",
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
