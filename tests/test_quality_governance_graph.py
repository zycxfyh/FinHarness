from __future__ import annotations

import unittest

from finharness.quality_governance_graph import run_quality_governance_graph

PASSED_CHECKS = [
    {"name": "task check", "command": ["task", "check"], "required": True, "status": "passed"},
    {
        "name": "task hardening:gate",
        "command": ["task", "hardening:gate"],
        "required": True,
        "status": "passed",
    },
    {
        "name": "task eval:redteam-boundary",
        "command": ["task", "eval:redteam-boundary"],
        "required": True,
        "status": "passed",
    },
]


class QualityGovernanceGraphTest(unittest.TestCase):
    def test_passed_checks_produce_non_blocked_decision(self) -> None:
        result = run_quality_governance_graph(checks=PASSED_CHECKS)
        final = result["final"]
        self.assertFalse(final["release_decision"]["release_blocked"])
        self.assertEqual(final["security_gate"]["ok"], True)
        self.assertEqual(final["redteam_gate"]["ok"], True)
        self.assertFalse(final["source"]["execution_allowed"])
        self.assertEqual(final["performance_baseline"]["status"], "within_budget")
        self.assertFalse(final["performance_baseline"]["release_blocking"])

    def test_failed_required_check_blocks_release(self) -> None:
        checks = [
            {**PASSED_CHECKS[0], "status": "failed", "returncode": 1},
            *PASSED_CHECKS[1:],
        ]
        result = run_quality_governance_graph(checks=checks)
        decision = result["final"]["release_decision"]
        self.assertTrue(decision["release_blocked"])
        self.assertIn("task check", decision["failed_required_checks"])

    def test_slow_check_is_tracked_without_release_blocking(self) -> None:
        checks = [
            {
                **PASSED_CHECKS[0],
                "duration_seconds": 12.5,
                "budget_seconds": 1.0,
            },
            *PASSED_CHECKS[1:],
        ]

        result = run_quality_governance_graph(checks=checks)
        final = result["final"]

        self.assertFalse(final["release_decision"]["release_blocked"])
        self.assertEqual(final["release_decision"]["performance_status"], "slow")
        self.assertEqual(final["performance_baseline"]["slow_check_count"], 1)
        self.assertEqual(final["performance_baseline"]["slow_checks"][0]["name"], "task check")
        self.assertFalse(final["performance_baseline"]["release_blocking"])


if __name__ == "__main__":
    unittest.main()
