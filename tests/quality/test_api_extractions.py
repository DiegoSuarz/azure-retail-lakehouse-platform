"""Pruebas de extracciones conservadas y defectos de calidad."""

import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from quality.api_extraction_input import ExtractionError, read_extraction
from quality.bcrpdata_rules import evaluate_bcrpdata
from quality.dummyjson_rules import evaluate_dummyjson

DUMMY = ROOT / (
    "data/apis/dummyjson/products/ingestion_date=2026-10-11/"
    "run_id=172c6634-a566-4ae8-bfc7-04ae228dae77"
)
BCRP = ROOT / (
    "data/apis/bcrpdata/exchange_rates/series_code=pd04638pd/"
    "ingestion_date=2026-10-11/"
    "run_id=e7d0e002-b3a6-4de3-8157-c2a3f818cd38"
)


class ApiExtractionTests(unittest.TestCase):
    def test_preserved_extractions_match_controls(self):
        manifest, responses, payloads = read_extraction(DUMMY)
        records = evaluate_dummyjson(manifest, responses, payloads)
        self.assertEqual(len(records), 38)
        self.assertTrue(all(row["status"] == "accepted" for row in records))

        manifest, responses, payloads = read_extraction(BCRP)
        records = evaluate_bcrpdata(manifest, responses, payloads)
        self.assertEqual(len(records), 195)
        self.assertTrue(all(row["status"] == "accepted" for row in records))
        self.assertEqual(sum(row["available"] for row in records), 184)
        self.assertEqual(
            sum(row["available"] is False for row in records), 11
        )

    def test_dummyjson_bad_pagination_blocks_extraction(self):
        manifest, responses, payloads = read_extraction(DUMMY)
        changed = deepcopy(responses)
        page = "category=laptops/page_000001.json"
        changed[page]["skip"] = 1

        with self.assertRaises(ExtractionError) as caught:
            evaluate_dummyjson(manifest, changed, payloads)
        self.assertEqual(caught.exception.code, "DQ014")
        self.assertEqual(responses[page]["skip"], 0)

    def test_dummyjson_bad_product_is_rejected(self):
        manifest, responses, payloads = read_extraction(DUMMY)
        changed = deepcopy(responses)
        page = "category=laptops/page_000001.json"
        changed[page]["products"][0]["stock"] = -1

        records = evaluate_dummyjson(manifest, changed, payloads)
        rejected = [row for row in records if row["status"] == "rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(len(records), 38)
        self.assertIn(
            "stock", {error["field"] for error in rejected[0]["errors"]}
        )

    def test_bcrpdata_bad_date_and_rate_are_rejected(self):
        manifest, responses, payloads = read_extraction(BCRP)
        for defect in ("date", "rate"):
            with self.subTest(defect=defect):
                changed = deepcopy(responses)
                period = changed["response.json"]["periods"][0]
                if defect == "date":
                    period["name"] = "31.Feb.26"
                else:
                    period["values"] = ["-1"]

                records = evaluate_bcrpdata(manifest, changed, payloads)
                rejected = [
                    row for row in records if row["status"] == "rejected"
                ]
                self.assertEqual(len(rejected), 1)
                self.assertEqual(len(records), 195)
                self.assertIn(
                    "DQ015",
                    {error["code"] for error in rejected[0]["errors"]},
                )

    def test_bcrpdata_duplicate_date_blocks_extraction(self):
        manifest, responses, payloads = read_extraction(BCRP)
        changed = deepcopy(responses)
        periods = changed["response.json"]["periods"]
        periods[1]["name"] = periods[0]["name"]

        with self.assertRaises(ExtractionError) as caught:
            evaluate_bcrpdata(manifest, changed, payloads)
        self.assertEqual(caught.exception.code, "DQ015")


if __name__ == "__main__":
    unittest.main(verbosity=2)
