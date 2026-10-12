"""Pruebas de las reglas de registros de API."""

import sys
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from quality.api_record_rules import evaluate_product, evaluate_rate


class ApiRecordTests(unittest.TestCase):
    def product(self):
        return {
            "id": 78,
            "title": "Producto de prueba",
            "category": "laptops",
            "price": Decimal("100.250"),
            "rating": Decimal("4.5"),
            "stock": 3,
        }

    def test_valid_product_preserves_precision_and_input(self):
        product = self.product()
        before = deepcopy(product)
        result = evaluate_product(product, "laptops")

        self.assertEqual(result["status"], "accepted")
        self.assertEqual(product, before)
        values = result["values"]
        self.assertEqual(
            values["external_price"].as_tuple(),
            Decimal("100.250").as_tuple(),
        )
        self.assertIsNone(values["external_brand"])
        self.assertIsNone(values["external_currency_code"])

        # El contrato actual no establece un mínimo para external_price.
        product["price"] = Decimal("-1.00")
        self.assertEqual(
            evaluate_product(product, "laptops")["status"], "accepted"
        )

    def test_invalid_product_fields_are_rejected(self):
        cases = (
            ("id", True),
            ("title", " "),
            ("category", "groceries"),
            ("price", "100.25"),
            ("price", Decimal("NaN")),
            ("rating", Decimal("5.1")),
            ("stock", -1),
            ("stock", True),
            ("brand", 123),
        )
        for field, value in cases:
            with self.subTest(field=field, value=str(value)):
                product = self.product()
                product[field] = value
                before = deepcopy(product)
                result = evaluate_product(product, "laptops")

                self.assertEqual(result["status"], "rejected")
                self.assertIsNone(result["values"])
                self.assertIn(
                    field, {error["field"] for error in result["errors"]}
                )
                self.assertTrue(
                    all(error["code"] == "DQ014" for error in result["errors"])
                )
                # Compara representaciones para incluir Decimal("NaN").
                self.assertEqual(repr(product), repr(before))

    def test_unavailable_rates_preserve_original_value(self):
        for raw in ("n.d.", "", " texto ", "NaN", "Infinity"):
            with self.subTest(raw=raw):
                result = evaluate_rate(raw)
                self.assertEqual(result["status"], "accepted")
                self.assertFalse(result["available"])
                self.assertIsNone(result["rate"])
                self.assertEqual(result["raw_value"], raw)
                self.assertEqual(result["errors"], [])

    def test_numeric_rates_require_positive_values(self):
        result = evaluate_rate("3.750")
        self.assertEqual(result["status"], "accepted")
        self.assertTrue(result["available"])
        self.assertEqual(
            result["rate"].as_tuple(), Decimal("3.750").as_tuple()
        )

        for raw in ("0", "-1", 3.75, None, True):
            with self.subTest(raw=raw):
                result = evaluate_rate(raw)
                self.assertEqual(result["status"], "rejected")
                self.assertIn(
                    "DQ015", {error["code"] for error in result["errors"]}
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
