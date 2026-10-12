"""Pruebas de calidad y conservación de eventos JSONL."""

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "quality/check_events.py"


class EventQualityTests(unittest.TestCase):
    def execute(self, source, output, baseline):
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT),
                "--batch-dir", str(source),
                "--output-dir", str(output),
                "--baseline", baseline,
            ],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "completed_for_scope")
        self.assertEqual(report["reconciliation"], "passed")
        self.assertFalse(report["state_modified"])
        summary = report["events"]
        self.assertEqual(
            summary["read"],
            sum(summary[key] for key in (
                "accepted", "rejected", "conflict", "pending", "duplicate",
            )),
        )
        return report

    def read_outputs(self, output, metadata):
        records = []
        for entry in metadata:
            path = output / entry["path"]
            payload = path.read_bytes()
            self.assertEqual(len(payload), entry["size_bytes"])
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(), entry["sha256"],
            )
            rows = pq.ParquetFile(path).read().to_pylist()
            self.assertEqual(len(rows), entry["row_count"])
            records.extend(rows)
        return records

    def create_batch(self, directory, events):
        directory.mkdir()
        payload = "".join(
            json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
            for event in events
        ).encode("utf-8")
        (directory / "changes.jsonl").write_bytes(payload)
        (directory / "manifest.json").write_text(
            json.dumps({
                "schema_version": 1,
                "batch_id": "event_test",
                "created_at": "2026-10-02T00:00:00.000Z",
                "files": {
                    "changes.jsonl": {
                        "row_count": len(events),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                },
            }),
            encoding="utf-8",
        )

    def test_invalid_scenarios_preserve_evidence(self):
        cases = (
            ("S13", "after_batch_001", "conflict", "DQ011"),
            ("S14", "after_batch_001", "conflict", "DQ011"),
            ("S15", "initial", "rejected", "DQ013"),
            ("S20", "initial", "rejected", "DQ012"),
        )
        for scenario, baseline, status, code in cases:
            with self.subTest(scenario=scenario):
                with tempfile.TemporaryDirectory() as temporary:
                    source = ROOT / "data/incremental/invalid" / scenario
                    output = Path(temporary) / "output"
                    report = self.execute(source, output, baseline)

                    self.assertEqual(report["events"]["read"], 1)
                    self.assertEqual(report["events"][status], 1)
                    self.assertEqual(report["events"]["accepted"], 0)
                    self.assertEqual(report["pending_files"], [])

                    records = self.read_outputs(output, report["quarantine_files"])
                    self.assertEqual(len(records), 1)
                    record = records[0]
                    self.assertEqual(record["status"], status)
                    self.assertIn(code, {error["code"] for error in record["errors"]})
                    self.assertIsNotNone(record["reference_content_json"])
                    self.assertEqual(
                        record["processing_run_id"], report["processing_run_id"],
                    )
                    self.assertIsNone(record["ingestion_run_id"])
                    self.assertEqual(
                        record["raw_record"],
                        (source / "changes.jsonl").read_bytes().decode("utf-8"),
                    )

    def test_pending_is_separate_from_quarantine(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "output"
            report = self.execute(
                ROOT / "data/incremental/functional/batch_002",
                output, "after_batch_001",
            )
            self.assertEqual(report["events"]["read"], 2)
            self.assertEqual(report["events"]["duplicate"], 1)
            self.assertEqual(report["events"]["pending"], 1)
            self.assertEqual(report["quarantine_files"], [])

            records = self.read_outputs(output, report["pending_files"])
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["status"], "pending")
            self.assertIn(
                "DQ011", {error["code"] for error in records[0]["errors"]},
            )

    def test_collisions_and_duplicates_inside_batch(self):
        path = ROOT / "data/incremental/functional/batch_001/changes.jsonl"
        original = json.loads(
            path.read_text(encoding="utf-8").splitlines()[0]
        )

        for variant in ("same_id_changed", "same_sequence_new_id", "identical"):
            with self.subTest(variant=variant):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    second = deepcopy(original)
                    if variant == "same_id_changed":
                        second["after"]["first_name"] += "_conflict"
                    elif variant == "same_sequence_new_id":
                        second["event_id"] = str(uuid4())

                    source = root / "input"
                    output = root / "output"
                    self.create_batch(source, [original, second])
                    report = self.execute(source, output, "initial")

                    if variant == "identical":
                        self.assertEqual(report["events"]["accepted"], 1)
                        self.assertEqual(report["events"]["duplicate"], 1)
                        self.assertEqual(report["quarantine_files"], [])
                        self.assertEqual(report["pending_files"], [])
                    else:
                        self.assertEqual(report["events"]["conflict"], 2)
                        self.assertEqual(report["events"]["accepted"], 0)
                        records = self.read_outputs(
                            output, report["quarantine_files"],
                        )
                        self.assertEqual(len(records), 2)
                        self.assertTrue(all(
                            record["status"] == "conflict" for record in records
                        ))


if __name__ == "__main__":
    unittest.main(verbosity=2)
