"""Pruebas de referencias y unicidad del mapeo externo."""

import csv
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "quality/check_product_mapping.py"
MAPPING = ROOT / "sources/reference/product_external_mapping.csv"
DUMMY = ROOT / (
    "data/apis/dummyjson/products/ingestion_date=2026-10-11/"
    "run_id=172c6634-a566-4ae8-bfc7-04ae228dae77"
)


class ProductMappingTests(unittest.TestCase):
    def execute(self, mapping, report, expected_exit):
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--mapping", str(mapping),
                "--dummyjson-run-dir", str(DUMMY),
                "--report", str(report),
            ],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(
            result.returncode, expected_exit, result.stdout + result.stderr
        )
        return json.loads(report.read_text(encoding="utf-8"))

    def test_valid_mapping_is_allowed(self):
        original = MAPPING.read_bytes()
        with tempfile.TemporaryDirectory() as temporary:
            report = self.execute(
                MAPPING, Path(temporary) / "report.json", 0
            )
            self.assertEqual(report["status"], "validated")
            self.assertTrue(report["incorporation_allowed"])
            self.assertEqual(
                report["records"],
                {"read": 6, "accepted": 6, "rejected": 0},
            )
            self.assertEqual(report["rejected_records"], [])
        self.assertEqual(MAPPING.read_bytes(), original)

    def test_invalid_associations_block_complete_mapping(self):
        cases = (
            ("missing_local", "product_id", 1),
            ("missing_external", "external_product_id", 1),
            ("duplicate_local", "product_id", 2),
            ("duplicate_external", "external_product_id", 2),
            ("missing_note", "mapping_note", 1),
        )
        original = MAPPING.read_bytes()

        for defect, expected_field, rejected_count in cases:
            with self.subTest(defect=defect):
                reader = csv.DictReader(
                    io.StringIO(original.decode("utf-8"), newline="")
                )
                columns = reader.fieldnames
                rows = list(reader)

                if defect.startswith("missing_") and defect != "missing_note":
                    rows[0][expected_field] = "999999"
                elif defect.startswith("duplicate_"):
                    rows[1][expected_field] = rows[0][expected_field]
                else:
                    rows[0]["mapping_note"] = " "

                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    mapping = root / "mapping.csv"
                    with mapping.open(
                        "w", encoding="utf-8", newline=""
                    ) as stream:
                        writer = csv.DictWriter(stream, fieldnames=columns)
                        writer.writeheader()
                        writer.writerows(rows)

                    before = mapping.read_bytes()
                    report = self.execute(mapping, root / "report.json", 1)
                    self.assertEqual(report["status"], "blocked")
                    self.assertFalse(report["incorporation_allowed"])
                    self.assertEqual(report["reconciliation"], "passed")
                    self.assertEqual(report["records"]["read"], 6)
                    self.assertEqual(
                        report["records"]["rejected"], rejected_count
                    )
                    self.assertEqual(
                        report["records"]["accepted"]
                        + report["records"]["rejected"], 6
                    )
                    self.assertEqual(
                        len(report["rejected_records"]), rejected_count
                    )
                    for record in report["rejected_records"]:
                        self.assertIn(
                            expected_field,
                            {error["field"] for error in record["errors"]},
                        )
                        self.assertTrue(all(
                            error["code"] == "DQ016"
                            for error in record["errors"]
                        ))
                    self.assertEqual(mapping.read_bytes(), before)

        self.assertEqual(MAPPING.read_bytes(), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
