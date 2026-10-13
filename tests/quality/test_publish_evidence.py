"""Comprueba que un paquete inválido no llegue a Azure CLI."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "quality/publish_evidence.py"
PACKAGE = ROOT / "data/publication/m6"


class EvidencePublicationTests(unittest.TestCase):
    def test_invalid_package_never_calls_azure(self):
        for defect in ("hash", "container"):
            with self.subTest(defect=defect):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    package = root / "package"
                    shutil.copytree(PACKAGE, package)
                    plan_path = package / "publication_plan.json"
                    plan = json.loads(plan_path.read_text(encoding="utf-8"))

                    if defect == "hash":
                        path = package / plan["files"][0]["local_path"]
                        path.write_bytes(path.read_bytes() + b"\n")
                        expected = "Hash diferente"
                    else:
                        plan["files"][0]["container"] = "bronze"
                        plan_path.write_text(
                            json.dumps(plan) + "\n", encoding="utf-8"
                        )
                        expected = "Contenedor incompatible"

                    fake_bin = root / "bin"
                    fake_bin.mkdir()
                    marker = root / "azure_called"
                    fake_az = fake_bin / "az"
                    fake_az.write_text(
                        '#!/bin/sh\n'
                        'touch "$AZURE_CALL_MARKER"\n'
                        'exit 99\n',
                        encoding="utf-8",
                    )
                    fake_az.chmod(0o755)

                    environment = os.environ.copy()
                    environment["PATH"] = (
                        str(fake_bin) + os.pathsep + environment["PATH"]
                    )
                    environment["AZURE_CALL_MARKER"] = str(marker)
                    report = root / "publication_report.json"

                    result = subprocess.run(
                        [
                            sys.executable, str(SCRIPT),
                            "--package-dir", str(package),
                            "--publish",
                            "--report", str(report),
                        ],
                        cwd=ROOT, env=environment,
                        capture_output=True, text=True,
                    )

                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(expected, result.stdout + result.stderr)
                    self.assertFalse(marker.exists())
                    self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
