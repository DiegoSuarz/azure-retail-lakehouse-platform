"""Pruebas locales de clasificación y cuarentena de pedidos nuevos."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "quality/check_new_orders.py"


class NewOrderQualityTests(unittest.TestCase):
    def execute_case(self, relative, output):
        source = ROOT / "data/incremental" / relative
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--batch-dir", str(source),
                "--output-dir", str(output),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        report_path = output / "report.json"
        self.assertTrue(
            report_path.is_file(), result.stdout + result.stderr,
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        return source, result, report

    def test_valid_orders_without_quarantine(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "valid"
            _, result, report = self.execute_case(
                "functional/batch_001", output,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(report["status"], "completed_for_scope")
            self.assertEqual(report["records_processed"], 4)
            self.assertFalse(report["events_evaluated"])
            self.assertEqual(report["event_count_not_evaluated"], 6)
            self.assertEqual(report["quarantine_files"], [])
            self.assertEqual(list(output.glob("*.parquet")), [])
            for entity in ("orders", "order_items"):
                self.assertEqual(
                    report["entities"][entity],
                    {"read": 2, "accepted": 2, "rejected": 0},
                )

    def test_invalid_order_is_excluded_completely(self):
        for scenario, original_code in (("S16", "DQ007"), ("S17", "DQ008")):
            with self.subTest(scenario=scenario):
                with tempfile.TemporaryDirectory() as temporary:
                    output = Path(temporary) / scenario
                    source, result, report = self.execute_case(
                        f"invalid/{scenario}", output,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(report["status"], "completed_for_scope")
                    self.assertEqual(report["reconciliation"], "passed")
                    self.assertEqual(report["records_processed"], 4)
                    self.assertEqual(len(report["quarantine_files"]), 2)

                    for entity in ("orders", "order_items"):
                        self.assertEqual(
                            report["entities"][entity],
                            {"read": 2, "accepted": 1, "rejected": 1},
                        )

                    for metadata in report["quarantine_files"]:
                        path = output / metadata["path"]
                        payload = path.read_bytes()
                        self.assertEqual(len(payload), metadata["size_bytes"])
                        self.assertEqual(
                            hashlib.sha256(payload).hexdigest(),
                            metadata["sha256"],
                        )
                        rows = pq.ParquetFile(path).read().to_pylist()
                        self.assertEqual(len(rows), metadata["row_count"])
                        self.assertEqual(len(rows), 1)
                        record = rows[0]

                        key = json.loads(record["business_key_json"])
                        self.assertEqual(key["order_id"], 2001)
                        self.assertEqual(record["status"], "rejected")
                        self.assertEqual(record["batch_id"], f"invalid_{scenario.lower()}")
                        self.assertIsNone(record["ingestion_run_id"])
                        self.assertEqual(
                            record["processing_run_id"],
                            report["processing_run_id"],
                        )

                        codes = {error["code"] for error in record["errors"]}
                        self.assertIn("DQ010", codes)
                        if record["entity"] == "order_items":
                            self.assertIn(original_code, codes)

                        original = (source / f"{record['entity']}.csv").read_bytes()
                        lines = original.decode("utf-8").splitlines(keepends=True)
                        self.assertEqual(
                            record["raw_record"],
                            lines[record["record_number"]],
                        )

    def test_bad_hash_blocks_before_business_processing(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "blocked"
            _, result, report = self.execute_case("invalid/S18", output)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(report["status"], "blocked")
            self.assertIsNone(report["records_processed"])
            self.assertNotIn("entities", report)
            self.assertEqual(report["quarantine_files"], [])
            self.assertEqual(list(output.glob("*.parquet")), [])
            self.assertIn("DQ002", {error["code"] for error in report["errors"]})


if __name__ == "__main__":
    unittest.main(verbosity=2)
