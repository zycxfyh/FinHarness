"""Behavioral contracts for the AUT3 delegated-review foundation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.autonomy_control import (
    AgentActionClass,
    AgentAutonomyLevel,
    AutonomyMandate,
)
from finharness.delegated_review import (
    DelegatedReviewRequest,
    aut3_runtime,
    build_decision_case,
    create_scenario,
    evaluate_delegated_review,
    load_delegated_review_result,
    write_delegated_review_result,
    write_scenario,
)
from finharness.statecore.proposals import (
    create_governed_proposal,
    revise_governed_proposal_scaffold,
)
from finharness.statecore.store import init_state_core


class DelegatedReviewVerticalSliceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipts = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.proposal = create_governed_proposal(
            proposal_id="prop_concentration",
            kind="concentration_review",
            claim="Review whether the concentrated position should be reduced.",
            evidence={"position_weight": 0.42},
            decision_scaffold={
                "decision_intent": "Choose a bounded concentration response.",
                "thesis": "Concentration exceeds the operator's review threshold.",
                "do_nothing_case": "Keep the current position and monitor risk.",
                "risk_if_wrong": "Reduction may crystallize tax and opportunity costs.",
            },
            source_refs=["capital-state://v1"],
            engine=self.engine,
            receipt_root=self.receipts,
        ).proposal

    def _scenario(self, case, *, uncertainty=0.20, notional_implication=500.0):
        return create_scenario(
            decision_case=case,
            kind="operator_sized_reduction",
            assumptions={"reduction_fraction": 0.10},
            metrics={"weight_before": 0.42, "weight_after": 0.38},
            uncertainty=uncertainty,
            notional_implication=notional_implication,
            calculation_version="concentration-scenario-v0",
            source_refs=(case.proposal_version.proposal_receipt_ref,),
            created_at_utc="2026-07-11T00:00:00+00:00",
        )

    def _mandate(self) -> AutonomyMandate:
        return AutonomyMandate(
            mandate_id="mandate_review",
            principal_id="principal:owner",
            agent_id="agent:capital",
            granted_autonomy=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            allowed_action_classes=(AgentActionClass.MAKE_PLANNING_DECISION,),
            constraints={
                "allowed_decisions": ["accept_for_planning", "reject", "defer"],
                "max_uncertainty": 0.30,
                "max_notional_implication": 1000.0,
            },
        )

    def _request(self, case, scenario, **changes):
        values = {
            "review_id": "delegated_review_001",
            "work_id": "work_001",
            "agent_id": "agent:capital",
            "decision_case_id": case.decision_case_id,
            "decision_case_version_id": case.case_version_id,
            "proposal_version_id": case.proposal_version.proposal_version_id,
            "scenario_ids": (scenario.scenario_id,),
            "selected_scenario_id": scenario.scenario_id,
            "decision": "accept_for_planning",
            "rationale": "The bounded reduction improves concentration without execution.",
            "uncertainty": scenario.uncertainty,
            "notional_implication": scenario.notional_implication,
            "source_refs": (scenario.scenario_version_id,),
        }
        values.update(changes)
        return DelegatedReviewRequest(**values)

    def test_mandate_contained_review_is_effective_but_never_execution(self) -> None:
        case = build_decision_case(proposal_id=self.proposal.proposal_id, engine=self.engine)
        scenario = self._scenario(case)
        result = evaluate_delegated_review(
            request=self._request(case, scenario),
            decision_case=case,
            scenarios=(scenario,),
            mandate=self._mandate(),
            runtime=aut3_runtime(
                world_state_ref=case.case_version_id,
                now_utc="2026-07-11T01:00:00+00:00",
            ),
        )

        self.assertEqual(result.disposition, "effective")
        self.assertTrue(result.effective_planning_decision)
        self.assertFalse(result.execution_allowed)
        self.assertFalse(result.authority_transition)
        self.assertFalse(result.admission.execution_allowed)

    def test_proposal_revision_invalidates_case_and_scenario_binding(self) -> None:
        old_case = build_decision_case(proposal_id=self.proposal.proposal_id, engine=self.engine)
        old_scenario = self._scenario(old_case)
        revise_governed_proposal_scaffold(
            proposal_id=self.proposal.proposal_id,
            scaffold_patch={"thesis": "Updated evidence changes the concentration thesis."},
            attester="owner@example.com",
            reason="Bind the review to newly assessed evidence.",
            engine=self.engine,
            receipt_root=self.receipts,
        )
        new_case = build_decision_case(proposal_id=self.proposal.proposal_id, engine=self.engine)

        result = evaluate_delegated_review(
            request=self._request(old_case, old_scenario),
            decision_case=new_case,
            scenarios=(old_scenario,),
            mandate=self._mandate(),
            runtime=aut3_runtime(world_state_ref=new_case.case_version_id),
        )

        self.assertNotEqual(old_case.case_version_id, new_case.case_version_id)
        self.assertEqual(result.disposition, "escalated")
        self.assertIn("stale_decision_case_version", result.escalation_reasons)
        self.assertIn("stale_proposal_version", result.escalation_reasons)

    def test_uncertainty_and_notional_limits_escalate_to_human(self) -> None:
        case = build_decision_case(proposal_id=self.proposal.proposal_id, engine=self.engine)
        scenario = self._scenario(case, uncertainty=0.60, notional_implication=2500.0)
        result = evaluate_delegated_review(
            request=self._request(case, scenario),
            decision_case=case,
            scenarios=(scenario,),
            mandate=self._mandate(),
            runtime=aut3_runtime(world_state_ref=case.case_version_id),
        )

        self.assertEqual(result.disposition, "escalated")
        self.assertIn("uncertainty_exceeds_mandate", result.escalation_reasons)
        self.assertIn("notional_exceeds_mandate", result.escalation_reasons)

    def test_agent_cannot_understate_selected_scenario_limits(self) -> None:
        case = build_decision_case(proposal_id=self.proposal.proposal_id, engine=self.engine)
        scenario = self._scenario(case, uncertainty=0.60, notional_implication=2500.0)
        result = evaluate_delegated_review(
            request=self._request(case, scenario, uncertainty=0.10, notional_implication=100.0),
            decision_case=case,
            scenarios=(scenario,),
            mandate=self._mandate(),
            runtime=aut3_runtime(world_state_ref=case.case_version_id),
        )

        self.assertEqual(result.disposition, "escalated")
        self.assertIn("scenario_limits_mismatch", result.escalation_reasons)
        self.assertIn("uncertainty_exceeds_mandate", result.escalation_reasons)
        self.assertIn("notional_exceeds_mandate", result.escalation_reasons)

    def test_runtime_must_name_the_exact_case_world_version(self) -> None:
        case = build_decision_case(proposal_id=self.proposal.proposal_id, engine=self.engine)
        scenario = self._scenario(case)
        result = evaluate_delegated_review(
            request=self._request(case, scenario),
            decision_case=case,
            scenarios=(scenario,),
            mandate=self._mandate(),
            runtime=aut3_runtime(world_state_ref="dcv_stale"),
        )

        self.assertEqual(result.disposition, "escalated")
        self.assertIn("runtime_world_state_mismatch", result.escalation_reasons)

    def test_receipts_survive_fresh_object_hydration(self) -> None:
        case = build_decision_case(proposal_id=self.proposal.proposal_id, engine=self.engine)
        scenario = self._scenario(case)
        scenario_ref = write_scenario(scenario, receipt_root=self.receipts)
        result = evaluate_delegated_review(
            request=self._request(case, scenario, source_refs=(scenario_ref,)),
            decision_case=case,
            scenarios=(scenario,),
            mandate=self._mandate(),
            runtime=aut3_runtime(world_state_ref=case.case_version_id),
        )
        result_ref = write_delegated_review_result(result, receipt_root=self.receipts)

        hydrated = load_delegated_review_result(
            result.review_id, receipt_root=Path(str(self.receipts))
        )
        self.assertEqual(hydrated, result)
        self.assertTrue((self.receipts / scenario_ref).is_file())
        self.assertTrue((self.receipts / result_ref).is_file())


if __name__ == "__main__":
    unittest.main()
