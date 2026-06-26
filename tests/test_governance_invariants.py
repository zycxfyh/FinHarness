"""Governance guardrail driver — runs the policy registry (EOS).

The enumerable governance rules live as declarative ``PolicyRule`` entries in
``tests/_policy_registry.py`` (id / owner / scope / source / check). This driver runs every
policy's check and reports failures by policy id, plus a meta-test that the registry stays
well-formed. ``task governance:check`` invokes this module.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests._policy_registry import POLICIES, _imported_modules


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
                try:
                    violations = policy.check()
                except Exception as exc:  # a raising check is itself a violation, by id
                    violations = [f"check raised {type(exc).__name__}: {exc}"]
                self.assertEqual(
                    violations, [], f"{policy.id} ({policy.owner}) violated: {violations}"
                )


class ImportBoundaryProbeBitesTest(unittest.TestCase):
    """Forcing function for the architecture probes (GOV-ARCH-003/004).

    The probes match forbidden dotted modules by prefix on `_imported_modules`. If that
    helper misses an import form, a forbidden dependency written that way silently evades
    the boundary — so assert all three import forms surface the canonical dotted module.
    """

    def _modules_for(self, source: str) -> set[str]:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
            handle.write(source + "\n")
            path = Path(handle.name)
        try:
            return _imported_modules(path)
        finally:
            path.unlink()

    def test_all_import_forms_surface_forbidden_module(self) -> None:
        forms = (
            "import finharness.review_read",
            "from finharness import review_read",
            "from finharness.review_read import read_proposal_timeline",
        )
        for source in forms:
            with self.subTest(form=source):
                modules = self._modules_for(source)
                self.assertTrue(
                    any(module.startswith("finharness.review_read") for module in modules),
                    f"{source!r} did not surface finharness.review_read; probe blind: {modules}",
                )


if __name__ == "__main__":
    unittest.main()
