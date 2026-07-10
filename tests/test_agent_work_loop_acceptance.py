"""Lock the known-red Agent Work Loop semantic acceptance baseline."""

from __future__ import annotations

import unittest

from scripts.run_agent_work_loop_acceptance import collect_acceptance_checks

EXPECTED_OPEN_CHECKS = {
    "all_stop_paths_reduced",
    "final_agent_run_receipt_linked",
    "max_steps_effective",
    "observation_driven_decision",
    "playbook_requirements_enforced",
    "real_tool_arguments",
    "result_searchable_by_work_id",
    "review_workspace_hydrated",
    "tool_result_refs_are_artifacts",
    "unavailable_tool_stop",
    "work_result_persisted",
}

EXPECTED_PASSING_CHECKS = {
    "context_snapshot_frozen",
    "evaluation_report_linked",
    "execution_boundary_closed",
    "max_tool_calls_effective",
}


class AgentWorkLoopAcceptanceBaselineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checks = collect_acceptance_checks()

    def test_acceptance_check_ids_are_unique_and_complete(self) -> None:
        ids = [check.check_id for check in self.checks]
        self.assertEqual(len(ids), 15)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), EXPECTED_OPEN_CHECKS | EXPECTED_PASSING_CHECKS)

    def test_known_open_contracts_remain_explicit(self) -> None:
        actual = {check.check_id for check in self.checks if not check.passed}
        self.assertEqual(actual, EXPECTED_OPEN_CHECKS)

    def test_real_green_contracts_are_not_downgraded(self) -> None:
        actual = {check.check_id for check in self.checks if check.passed}
        self.assertEqual(actual, EXPECTED_PASSING_CHECKS)

    def test_every_check_reports_repository_evidence(self) -> None:
        for check in self.checks:
            with self.subTest(check_id=check.check_id):
                self.assertTrue(check.description.strip())
                self.assertTrue(check.evidence.strip())


if __name__ == "__main__":
    unittest.main()
