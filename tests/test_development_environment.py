from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "scripts" / "check_development_environment.py"


class DevelopmentEnvironmentTest(unittest.TestCase):
    def test_doctor_resolves_editable_package_without_pythonpath(self) -> None:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        completed = subprocess.run(
            [sys.executable, str(DOCTOR)],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        report = json.loads(completed.stdout)
        self.assertTrue(report["ok"])
        self.assertIsNone(report["pythonpath"])
        self.assertEqual(
            Path(report["module_file"]).resolve().parent,
            (ROOT / "src" / "finharness").resolve(),
        )
        self.assertEqual(Path(report["environment"]).resolve(), (ROOT / ".venv").resolve())

    def test_active_project_configuration_does_not_inject_pythonpath(self) -> None:
        paths = [
            ROOT / "Taskfile.yml",
            ROOT / "mise.toml",
            ROOT / "frontend" / "tests" / "browser" / "cockpit_smoke.test.cjs",
            ROOT / "frontend" / "tests" / "browser" / "local_review_mode.test.cjs",
        ]
        for path in paths:
            with self.subTest(path=path):
                content = path.read_text(encoding="utf-8")
                self.assertIsNone(re.search(r"(?m)^\s*PYTHONPATH\s*[:=]", content))

    def test_direct_smoke_entrypoint_does_not_require_repository_root_on_path(self) -> None:
        content = (ROOT / "scripts" / "run_local_review_smoke_server.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("from scripts.", content)
        self.assertNotIn("sys.path.", content)


if __name__ == "__main__":
    unittest.main()
