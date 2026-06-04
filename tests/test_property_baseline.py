from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_proposal import build_sample_validation_bundle

from finharness.proposal import build_proposal_bundle_from_validation_snapshot
from finharness.quality_governance_graph import run_quality_governance_graph
from finharness.repo_intelligence import build_file_inventory, classify_security_surface
from finharness.risk_gate import build_risk_gate_bundle_from_proposal_snapshot


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
        for failed_index in range(len(base)):
            checks = [
                {
                    **item,
                    "status": "failed" if index == failed_index else "passed",
                    "returncode": 1 if index == failed_index else 0,
                }
                for index, item in enumerate(base)
            ]
            decision = run_quality_governance_graph(checks=checks)["final"]["release_decision"]
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
            ["src/finharness/execution.py"],
            ["src/finharness/risk_gate.py"],
            [".github/workflows/security.yml"],
            ["docs/ordinary.md"],
        ]
        for changed_files in samples:
            surface = classify_security_surface(changed_files)
            self.assertFalse(surface["execution_allowed"])
            if changed_files[0] != "docs/ordinary.md":
                self.assertTrue(surface["requires_human_review"])

    def test_risk_gate_live_boundary_never_defaults_to_allowed(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        contexts = [
            {"requested_execution_mode": "live"},
            {"live_execution_allowed": True},
            {"requested_execution_mode": "paper"},
        ]
        for context in contexts:
            bundle = build_risk_gate_bundle_from_proposal_snapshot(
                proposal_bundle.snapshot,
                context=context,
            )
            self.assertFalse(bundle.snapshot.execution_allowed)
            self.assertTrue(
                all(not decision.live_execution_allowed for decision in bundle.decisions)
            )


if __name__ == "__main__":
    unittest.main()
