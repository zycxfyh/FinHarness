"""Focused runner for current documentation fact policies."""

from __future__ import annotations

import unittest

from tests._policy_registry import POLICIES

DOC_POLICY_PREFIX = "GOV-DOCS-"


class CurrentDocsFactPolicyTest(unittest.TestCase):
    def test_current_docs_policies_hold(self) -> None:
        policies = [policy for policy in POLICIES if policy.id.startswith(DOC_POLICY_PREFIX)]
        self.assertGreaterEqual(len(policies), 1, "No GOV-DOCS policies registered")
        for policy in policies:
            with self.subTest(policy=policy.id):
                self.assertEqual([], policy.check())


if __name__ == "__main__":
    unittest.main()
