"""Lock the known-red Agent Work Loop semantic acceptance baseline."""

from __future__ import annotations

import unittest

from scripts.run_agent_work_loop_acceptance import collect_acceptance_checks

EXPECTED_OPEN_CHECKS: set[str] = set()

EXPECTED_PASSING_CHECKS = {
    "all_stop_paths_reduced",
    "context_snapshot_frozen",
    "evaluation_report_linked",
    "execution_boundary_closed",
    "final_agent_run_receipt_linked",
    "max_steps_effective",
    "max_tool_calls_effective",
    "observation_driven_decision",
    "playbook_requirements_enforced",
    "real_tool_arguments",
    "result_searchable_by_work_id",
    "review_workspace_hydrated",
    "tool_result_refs_are_artifacts",
    "unavailable_tool_stop",
    "work_result_persisted",
}


class AgentWorkLoopAcceptanceBaselineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checks = collect_acceptance_checks()

    def test_all_contracts_are_either_open_or_passing(self) -> None:
        ids = {check.check_id for check in self.checks}
        self.assertEqual(ids, EXPECTED_OPEN_CHECKS | EXPECTED_PASSING_CHECKS)

    def test_known_open_contracts_remain_explicit(self) -> None:
        actual = {check.check_id for check in self.checks if not check.passed}
        self.assertEqual(actual, EXPECTED_OPEN_CHECKS)

    def test_real_green_contracts_are_not_downgraded(self) -> None:
        actual = {check.check_id for check in self.checks if check.passed}
        self.assertEqual(actual, EXPECTED_PASSING_CHECKS)
