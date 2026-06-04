from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness.governance_dashboard import (
    build_governance_dashboard,
    write_governance_dashboard_outputs,
)


class GovernanceDashboardTest(unittest.TestCase):
    def test_dashboard_aggregates_receipts_without_authorizing_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            quality_ref = root / "data" / "receipts" / "quality-governance" / "latest.json"
            hardening_ref = root / "data" / "receipts" / "hardening" / "latest-hardening-gate.json"
            quality_ref.parent.mkdir(parents=True)
            hardening_ref.parent.mkdir(parents=True)
            quality_ref.write_text(
                """
{
  "check_results": [
    {"name": "task check", "status": "passed", "duration_seconds": 1.0, "budget_seconds": 180.0},
    {
      "name": "task hardening:gate",
      "status": "passed",
      "duration_seconds": 1.0,
      "budget_seconds": 90.0
    },
    {
      "name": "task eval:redteam-boundary",
      "status": "passed",
      "duration_seconds": 1.0,
      "budget_seconds": 45.0
    }
  ],
  "performance_baseline": {"status": "within_budget", "execution_allowed": false}
}
""",
                encoding="utf-8",
            )
            hardening_ref.write_text(
                """
{
  "generated_at": "2026-06-04T00:00:00Z",
  "execution_allowed": false,
  "release_blocked": false,
  "checks": [{"tool": "gitleaks", "returncode": 0, "release_blocked": false}]
}
""",
                encoding="utf-8",
            )

            repo_final = {
                "inventory_summary": {"file_count": 3, "total_lines": 30},
                "blast_radius": {
                    "changed_files": ["src/finharness/example.py"],
                    "required_checks": ["task check"],
                },
                "security_surface": {"requires_human_review": False, "execution_allowed": False},
                "outputs": {"receipt": str(root / "repo.json")},
            }
            preflight_final = {
                "quality": {
                    "receipt_ref": str(quality_ref),
                    "release_decision": {
                        "decision": "passed",
                        "release_blocked": False,
                        "failed_required_checks": [],
                        "requires_human_review": False,
                        "performance_status": "within_budget",
                    },
                },
                "release_gate": {
                    "release_ready": True,
                    "release_blocked": False,
                    "missing": [],
                    "requires_human_review": False,
                    "execution_allowed": False,
                },
                "receipt_ref": str(root / "preflight.json"),
            }

            with (
                patch(
                    "finharness.governance_dashboard.run_repo_intelligence_graph",
                    return_value={"final": repo_final},
                ),
                patch(
                    "finharness.governance_dashboard.run_release_preflight_graph",
                    return_value={"final": preflight_final},
                ),
            ):
                dashboard = build_governance_dashboard(root=root)

            self.assertEqual(dashboard["dashboard_status"], "ready")
            self.assertFalse(dashboard["execution_allowed"])
            self.assertFalse(dashboard["hardening_gate"]["release_blocked"])
            self.assertTrue(dashboard["redteam_boundary"]["ok"])

    def test_dashboard_outputs_json_and_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dashboard = {
                "generated_at": "2026-06-04T00:00:00Z",
                "repo_intelligence": {
                    "inventory_summary": {"file_count": 1, "total_lines": 2},
                    "changed_surface": [],
                    "required_checks": ["task check"],
                },
                "quality_governance": {
                    "decision": "passed",
                    "release_blocked": False,
                    "performance_status": "within_budget",
                },
                "release_preflight": {
                    "release_ready": True,
                    "release_blocked": False,
                },
                "hardening_gate": {"status": "passed"},
                "redteam_boundary": {"status": "passed"},
                "requires_human_review": False,
                "execution_allowed": False,
                "dashboard_status": "ready",
                "mermaid": "flowchart TD\\n  a --> b",
            }
            outputs = write_governance_dashboard_outputs(dashboard, root=root)

            self.assertTrue(Path(outputs["receipt"]).exists())
            self.assertTrue(Path(outputs["report"]).exists())
            self.assertIn("Governance Dashboard", Path(outputs["report"]).read_text())


if __name__ == "__main__":
    unittest.main()
