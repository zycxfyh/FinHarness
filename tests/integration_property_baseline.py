from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.quality_governance_graph import run_quality_governance_graph
from finharness.repo_intelligence import build_file_inventory, classify_security_surface


class PropertyBaselineTest(unittest.TestCase):
    def test_quality_decision_blocks_every_required_failure_combination(self) -> None:
        base = [
            {"name": "task check", "command": ["task", "check"], "required": True},
            {
                "name": "task hardening:gate",
                "command": ["task", "hardening:gate"],
                "required": True,
            },
            {
                "name": "task eval:redteam-boundary",
                "command": ["task", "eval:redteam-boundary"],
                "required": True,
            },
        ]
        cached_repo_intelligence = run_quality_governance_graph(checks=base)[
            "repo_intelligence"
        ]
        for failed_index in range(len(base)):
            checks = [
                {
                    **item,
                    "status": "failed" if index == failed_index else "passed",
                    "returncode": 1 if index == failed_index else 0,
                }
                for index, item in enumerate(base)
            ]
            decision = run_quality_governance_graph(
                checks=checks,
                repo_intelligence=cached_repo_intelligence,
            )["final"]["release_decision"]
            self.assertTrue(decision["release_blocked"])
            self.assertIn(base[failed_index]["name"], decision["failed_required_checks"])
            self.assertFalse(decision["execution_allowed"])

    def test_repo_intelligence_excludes_env_and_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("SECRET=value\n", encoding="utf-8")
            (root / ".env.example").write_text("EXAMPLE=value\n", encoding="utf-8")
            (root / "data" / "receipts").mkdir(parents=True)
            (root / "data" / "receipts" / "secret.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "visible.py").write_text("print('ok')\n", encoding="utf-8")

            paths = {item["path"] for item in build_file_inventory(root)}

            self.assertNotIn(".env", paths)
            self.assertIn(".env.example", paths)
            self.assertNotIn("data/receipts/secret.json", paths)

    def test_security_surface_never_authorizes_execution_for_high_risk_files(self) -> None:
        samples = [
            ["src/finharness/execution/__init__.py"],
            ["src/finharness/risk_gate/__init__.py"],
            [".github/workflows/security.yml"],
            ["docs/ordinary.md"],
        ]
        for changed_files in samples:
            surface = classify_security_surface(changed_files)
            self.assertFalse(surface["execution_allowed"])
            if changed_files[0] != "docs/ordinary.md":
                self.assertTrue(surface["requires_human_review"])

if __name__ == "__main__":
    unittest.main()
