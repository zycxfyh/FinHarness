from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.project_governance_adapter import (
    STAGE_COMPATIBILITY,
    run_finharness_project_governance_adapter,
)


def _write_receipt(path: Path) -> None:
    payload = {
        "workflow": "langgraph_project_governance_loop_v1",
        "project": {"project_name": "finharness", "project_root": "/tmp/finharness"},
        "stage_parity": {
            "cognitive_intake": {
                "v1_status": "stage_parity_met",
                "feature_parity_status": "feature_parity_met",
                "mapped_finharness_object": "cognitive_graph.py",
            },
            "repo_observation": {
                "v1_status": "stage_parity_met",
                "feature_parity_status": "feature_parity_met",
                "mapped_finharness_object": "repo_intelligence_graph.py",
            },
            "quality_gate": {
                "v1_status": "stage_parity_met",
                "feature_parity_status": "feature_parity_met",
                "mapped_finharness_object": "quality_governance_graph.py",
            },
            "delivery_receipt": {
                "v1_status": "stage_parity_met",
                "feature_parity_status": "feature_parity_met",
                "mapped_finharness_object": "engineering_delivery_graph.py",
            },
        },
        "quality_gate": {
            "decision": "blocked_checks_not_run",
            "quality_claimed": False,
            "checks_executed": False,
            "security_hardening_gate": {"status": "not_cleared"},
            "redteam_boundary_gate": {"status": "not_cleared"},
            "release_gate": {"release_blocked": True},
        },
        "cognitive_intake": {
            "artifact_contract": {
                "contract_version": "project_governance_cognitive_artifact_contract_v1",
            },
            "artifact_plan": {"artifact_count": 6},
        },
        "delivery_model": {
            "decision": "blocked_by_quality_gate",
            "review_hook": {"required": True},
            "local_checks_gate": {"status": "blocked_checks_not_run"},
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class ProjectGovernanceAdapterTest(unittest.TestCase):
    def test_adapter_writes_compatibility_receipt_from_workstation_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "finharness"
            source = Path(tmp) / "workstation" / "finharness.json"
            _write_receipt(source)

            result = run_finharness_project_governance_adapter(
                root=root,
                workstation_receipt_path=source,
                write_receipt=True,
            )

            self.assertEqual(result["status"], "adapted")
            self.assertFalse(result["quality_summary"]["quality_claimed"])
            self.assertEqual(result["cognitive_summary"]["artifact_count"], 6)
            self.assertEqual(
                set(result["stage_statuses"]),
                {
                    "cognitive_intake",
                    "repo_observation",
                    "quality_gate",
                    "delivery_receipt",
                },
            )
            receipt = root / "data" / "receipts" / "project-governance-adapter" / "latest.json"
            self.assertTrue(receipt.exists())
            written = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(written["workflow"], "finharness_project_governance_adapter_v1")
            self.assertEqual(written["receipt_ref"], str(receipt))

    def test_adapter_preserves_existing_finharness_contract_names(self) -> None:
        stages = {item["stage"]: item for item in STAGE_COMPATIBILITY}

        self.assertEqual(stages["repo_observation"]["taskfile_entrypoint"], "repo:intelligence")
        self.assertEqual(stages["quality_gate"]["public_api"], "run_quality_governance_graph")
        self.assertIn(
            "data/receipts/repo-intelligence/latest.json",
            stages["repo_observation"]["current_outputs"],
        )
        self.assertIn(
            "data/receipts/cognitive-graph/*.json",
            stages["cognitive_intake"]["current_outputs"],
        )

    def test_missing_workstation_receipt_does_not_claim_adapter_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "finharness"
            missing = Path(tmp) / "missing.json"

            result = run_finharness_project_governance_adapter(
                root=root,
                workstation_receipt_path=missing,
                write_receipt=False,
            )

            self.assertEqual(result["status"], "missing_workstation_receipt")
            self.assertFalse(result["workstation_receipt_present"])
            self.assertTrue(result["not_claimed"])


if __name__ == "__main__":
    unittest.main()
