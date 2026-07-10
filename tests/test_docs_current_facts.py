"""Focused runner for current documentation fact policies."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from tests._policy_registry import POLICIES

DOC_POLICY_PREFIX = "GOV-DOCS-"
ROOT = Path(__file__).resolve().parents[1]


def _check_call_count(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_check"
    )


class CurrentDocsFactPolicyTest(unittest.TestCase):
    def test_current_docs_policies_hold(self) -> None:
        policies = [policy for policy in POLICIES if policy.id.startswith(DOC_POLICY_PREFIX)]
        self.assertGreaterEqual(len(policies), 1, "No GOV-DOCS policies registered")
        for policy in policies:
            with self.subTest(policy=policy.id):
                self.assertEqual([], policy.check())

    def test_financial_terminology_map_keeps_authority_non_claims(self) -> None:
        doc = ROOT / "docs" / "reference" / "financial-terminology-map.md"
        text = doc.read_text(encoding="utf-8")
        required_terms = [
            "Investment Policy Statement",
            "CapitalMandate",
            "AgentAuthorityGrant",
            "ActionIntentCandidate",
            "ActionIntentAuthorityBinding",
            "ActionIntentPreflight",
            "TradePlanCandidate",
            "OrderTicketCandidate",
            "BrokerSubmissionGate",
            "Regulatory analogy is not regulatory status.",
            "A receipt is evidence, not authorization.",
            "Preflight pass is not trade approval.",
            "Broker submission is not guaranteed execution.",
        ]
        for term in required_terms:
            with self.subTest(term=term):
                self.assertIn(term, text)

    def test_agent_smoke_check_counts_match_framework_index(self) -> None:
        framework = (ROOT / "docs" / "architecture" / "framework-index.md").read_text(
            encoding="utf-8"
        )
        operating_count = _check_call_count(
            ROOT / "scripts" / "run_agent_operating_surface_smoke.py"
        )
        work_count = _check_call_count(ROOT / "scripts" / "run_agent_work_loop_smoke.py")

        self.assertEqual(23, operating_count)
        self.assertEqual(18, work_count)
        self.assertIn(
            f"`run_agent_operating_surface_smoke.py` ({operating_count} checks)", framework
        )
        self.assertIn(f"`run_agent_work_loop_smoke.py` ({work_count} structural checks)", framework)

    def test_agent_work_loop_status_is_not_overclaimed(self) -> None:
        framework = (ROOT / "docs" / "architecture" / "framework-index.md").read_text(
            encoding="utf-8"
        )
        smoke = (ROOT / "scripts" / "run_agent_work_loop_smoke.py").read_text(encoding="utf-8")

        self.assertIn("Agent Work Loop is not semantically closed", framework)
        former_delivery_claim = "Wave 0" + "\N{EN DASH}" + "2.2 delivered"
        self.assertNotIn(former_delivery_claim, framework)
        self.assertNotIn("Agent Work Loop is operational", smoke)
        self.assertIn("semantic loop closure remains pending", smoke)

    def test_agent_work_loop_plan_records_unmet_acceptance(self) -> None:
        plan = (ROOT / "docs" / "architecture" / "agent-work-loop-plan.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("acceptance criteria not met", plan)
        self.assertIn("Deterministic Work Orchestrator: scaffolded", plan)
        self.assertIn("Agent Work Loop: not semantically closed", plan)
        self.assertIn("task agent:work-loop-acceptance", plan)
        self.assertIn("4/15 contracts pass and 11 remain", plan)

    def test_execution_interface_records_enforced_capabilities(self) -> None:
        interfaces = (ROOT / "docs" / "reference" / "interfaces.md").read_text(encoding="utf-8")
        system_map = (ROOT / "docs" / "architecture" / "system-map.md").read_text(encoding="utf-8")
        self.assertIn("| ExecutionKernelInterface |", interfaces)
        self.assertNotIn("no execution endpoints", interfaces)
        self.assertIn("service boundary fail closed", system_map)
        self.assertIn("拒绝 live submit 与 credential 管理", system_map)


if __name__ == "__main__":
    unittest.main()
