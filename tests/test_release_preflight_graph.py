from __future__ import annotations

import unittest

from finharness.release_preflight_graph import run_release_preflight_graph


class ReleasePreflightGraphTest(unittest.TestCase):
    def test_preflight_records_supply_chain_and_quality_evidence(self) -> None:
        result = run_release_preflight_graph()
        final = result["final"]
        self.assertEqual(final["source"]["graph"], "release_preflight_graph")
        self.assertTrue(final["supply_chain"]["dependabot_config_present"])
        self.assertTrue(final["supply_chain"]["codeowners_present"])
        self.assertTrue(final["supply_chain"]["codeql_workflow_present"])
        self.assertTrue(final["supply_chain"]["scorecard_workflow_present"])
        self.assertTrue(final["supply_chain"]["fuzz_workflow_present"])
        self.assertIn(
            ".github/workflows/fuzz.yml",
            final["supply_chain"]["workflow_refs_present"],
        )
        self.assertFalse(final["release_gate"]["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
