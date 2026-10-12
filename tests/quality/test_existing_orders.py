"""Comprueba conflictos y duplicados contra la referencia inicial."""

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "quality"))
from reference_data import load_initial_reference


class ExistingOrderTests(unittest.TestCase):
    def setUp(self):
        self.reference = load_initial_reference()
        self.original_hashes = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ROOT / "data/initial").iterdir()
            if path.is_file()
        }

    def tearDown(self):
        current = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (ROOT / "data/initial").iterdir()
            if path.is_file()
        }
        self.assertEqual(current, self.original_hashes)

    def run_checker(self, source, output):
        result = subprocess.run(
            [
                sys.executable, str(ROOT / "quality/check_new_orders.py"),
                "--batch-dir", str(source),
                "--output-dir", str(output),
            ],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(
            (output / "report.json").read_text(encoding="utf-8")
        )
        self.assertEqual(report["status"], "completed_for_scope")
        self.assertEqual(report["reconciliation"], "passed")
        return report

    def create_replay(self, directory, variant):
        directory.mkdir()
        order = next(
            dict(row) for row in self.reference["orders"]
            if int(row["order_id"]) == 4
        )
        items = [
            dict(row) for row in self.reference["order_items"]
            if int(row["order_id"]) == 4
        ]
        if variant == "changed_line":
            items[0]["quantity"] = str(int(items[0]["quantity"]) + 1)
        elif variant == "missing_line":
            items.pop()

        files = {}
        for filename, rows in (("orders.csv", [order]), ("order_items.csv", items)):
            path = directory / filename
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            files[filename] = {
                "row_count": len(rows),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }

        (directory / "manifest.json").write_text(
            json.dumps({
                "schema_version": 1,
                "batch_id": f"replay_{variant}",
                "created_at": "2026-10-02T00:00:00.000Z",
                "files": files,
            }),
            encoding="utf-8",
        )

    def test_s19_preserves_conflict_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            report = self.run_checker(
                ROOT / "data/incremental/invalid/S19", output,
            )
            self.assertEqual(report["entities"]["orders"], {
                "read": 1, "accepted": 0, "rejected": 0,
                "conflict": 1, "duplicate": 0,
            })
            self.assertEqual(report["entities"]["order_items"], {
                "read": 4, "accepted": 0, "rejected": 4,
                "conflict": 0, "duplicate": 0,
            })

            records = []
            for metadata in report["quarantine_files"]:
                path = output / metadata["path"]
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    metadata["sha256"],
                )
                rows = pq.ParquetFile(path).read().to_pylist()
                self.assertEqual(len(rows), metadata["row_count"])
                records.extend(rows)

            self.assertEqual(len(records), 5)
            order = next(row for row in records if row["entity"] == "orders")
            self.assertEqual(order["status"], "conflict")
            codes = {error["code"] for error in order["errors"]}
            self.assertTrue({"DQ006", "DQ009"} <= codes)

            reference = json.loads(order["reference_content_json"])
            self.assertEqual(reference["order"]["status"], "pending")
            self.assertEqual(len(reference["order_items"]), 4)
            self.assertIn(",confirmed,", order["raw_record"])

            for row in records:
                self.assertEqual(
                    json.loads(row["business_key_json"])["order_id"], 4,
                )
                if row["entity"] == "order_items":
                    self.assertEqual(row["status"], "rejected")
                    self.assertIn("DQ010", {error["code"] for error in row["errors"]})

    def test_duplicate_requires_complete_identical_content(self):
        for variant in ("identical", "changed_line", "missing_line"):
            with self.subTest(variant=variant):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    source = root / "input"
                    output = root / "output"
                    self.create_replay(source, variant)
                    report = self.run_checker(source, output)

                    if variant == "identical":
                        self.assertEqual(report["entities"]["orders"], {
                            "read": 1, "accepted": 0, "rejected": 0,
                            "conflict": 0, "duplicate": 1,
                        })
                        self.assertEqual(report["entities"]["order_items"], {
                            "read": 4, "accepted": 0, "rejected": 0,
                            "conflict": 0, "duplicate": 4,
                        })
                        self.assertEqual(report["quarantine_files"], [])
                        self.assertEqual(list(output.glob("*.parquet")), [])
                    else:
                        orders = report["entities"]["orders"]
                        items = report["entities"]["order_items"]
                        self.assertEqual(orders["conflict"], 1)
                        self.assertEqual(orders["accepted"], 0)
                        self.assertEqual(orders["duplicate"], 0)
                        self.assertEqual(items["accepted"], 0)
                        self.assertEqual(items["duplicate"], 0)
                        self.assertEqual(items["rejected"], items["read"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
