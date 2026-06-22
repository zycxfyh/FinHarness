"""Governance guardrail driver — runs the policy registry (EOS).

The enumerable governance rules live as declarative ``PolicyRule`` entries in
``tests/_policy_registry.py`` (id / owner / scope / source / check). This driver runs every
policy's check and reports failures by policy id, plus a meta-test that the registry stays
well-formed. ``task governance:check`` invokes this module.
"""

from __future__ import annotations

import unittest

from tests._policy_registry import POLICIES


class GovernancePolicyRegistryTest(unittest.TestCase):
    def test_registry_is_well_formed(self) -> None:
        ids = [policy.id for policy in POLICIES]
        self.assertEqual(len(ids), len(set(ids)), "policy ids must be unique")
        for policy in POLICIES:
            for field in ("id", "owner", "scope", "source", "description"):
                self.assertTrue(getattr(policy, field).strip(), f"{policy.id}: {field} required")
            self.assertTrue(callable(policy.check), f"{policy.id}: check must be callable")

    def test_all_policies_hold(self) -> None:
        for policy in POLICIES:
            with self.subTest(policy=policy.id):
                violations = policy.check()
                self.assertEqual(
                    violations, [], f"{policy.id} ({policy.owner}) violated: {violations}"
                )


if __name__ == "__main__":
    unittest.main()
