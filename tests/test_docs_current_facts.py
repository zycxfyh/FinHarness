"""Focused runner for current documentation fact policies."""

from __future__ import annotations

from pathlib import Path
import unittest

from tests._policy_registry import POLICIES

DOC_POLICY_PREFIX = "GOV-DOCS-"
ROOT = Path(__file__).resolve().parents[1]


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


if __name__ == "__main__":
    unittest.main()
