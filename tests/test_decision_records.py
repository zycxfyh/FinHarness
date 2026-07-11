"""Canonical ProposalVersion-bound DecisionRecord contracts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session, select

from finharness.autonomy_control import (
    AgentActionClass,
    AgentAutonomyLevel,
    AutonomyMandate,
)
from finharness.decision_records import (
    record_planning_decision,
    resolve_decision_validity,
)
from finharness.delegated_review import (
    DelegatedReviewRequest,
    aut3_runtime,
    build_decision_case,
    create_scenario,
    evaluate_delegated_review,
    write_delegated_review_result,
)
from finharness.statecore.models import DecisionRecord
from finharness.statecore.proposals import (
    create_governed_proposal,
    revise_governed_proposal_scaffold,
)
from finharness.statecore.store import init_state_core


class DecisionRecordVerticalSliceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipts = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.proposal_id = create_governed_proposal(
            proposal_id="prop_decision_record",
            kind="concentration_review",
            claim="Choose a bounded response to concentration.",
            evidence={"position_weight": 0.42},
            decision_scaffold={
                "decision_intent": "Choose a concentration response.",
                "thesis": "Current concentration exceeds the review threshold.",
                "do_nothing_case": "Hold and monitor the current position.",
                "risk_if_wrong": "A reduction can crystallize tax and opportunity costs.",
            },
            source_refs=["capital-state://v1"],
            engine=self.engine,
            receipt_root=self.receipts,
        ).proposal.proposal_id

    def _case_and_scenario(self):
        case = build_decision_case(proposal_id=self.proposal_id, engine=self.engine)
        scenario = create_scenario(
            decision_case=case,
            kind="operator_sized_reduction",
            assumptions={"reduction_fraction": 0.10},
            metrics={"weight_before": 0.42, "weight_after": 0.38},
            uncertainty=0.20,
            notional_implication=500.0,
            calculation_version="concentration-scenario-v0",
            created_at_utc="2026-07-12T00:00:00+00:00",
        )
        return case, scenario

    def _mandate(self) -> AutonomyMandate:
        return AutonomyMandate(
            mandate_id="mandate_decision_record",
            principal_id="principal:owner",
            agent_id="agent:capital",
            granted_autonomy=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            allowed_action_classes=(AgentActionClass.MAKE_PLANNING_DECISION,),
            constraints={
                "allowed_decisions": ["accept_for_planning"],
                "max_uncertainty": 0.30,
                "max_notional_implication": 1000.0,
            },
        )

    def test_human_decision_binds_exact_versions_without_execution(self) -> None:
        case, scenario = self._case_and_scenario()
        write = record_planning_decision(
            decision_case=case,
            scenario=scenario,
            decision="accepted_for_planning",
            reason="The bounded scenario is ready for planning review.",
            actor_id="owner@example.com",
            actor_identity_class="human",
            engine=self.engine,
            receipt_root=self.receipts,
            created_at_utc="2026-07-12T01:00:00+00:00",
        )

        self.assertEqual(write.validity.status, "effective")
        self.assertEqual(
            write.decision_record.proposal_version_id,
            case.proposal_version.proposal_version_id,
        )
        self.assertEqual(write.decision_record.scenario_version_id, scenario.scenario_version_id)
        self.assertFalse(write.decision_record.execution_allowed)
        self.assertTrue((self.receipts.parent / write.receipt_ref).is_file())

    def test_material_revision_deterministically_supersedes_old_decision(self) -> None:
        old_case, scenario = self._case_and_scenario()
        write = record_planning_decision(
            decision_case=old_case,
            scenario=scenario,
            decision="accepted_for_planning",
            reason="Record the decision against the current evidence.",
            actor_id="owner@example.com",
            actor_identity_class="human",
            engine=self.engine,
            receipt_root=self.receipts,
        )
        revise_governed_proposal_scaffold(
            proposal_id=self.proposal_id,
            scaffold_patch={"thesis": "New evidence materially changes the thesis."},
            attester="owner@example.com",
            reason="Material evidence revision.",
            engine=self.engine,
            receipt_root=self.receipts,
        )
        current_case = build_decision_case(proposal_id=self.proposal_id, engine=self.engine)

        validity = resolve_decision_validity(decision_case=current_case, engine=self.engine)

        self.assertEqual(validity.status, "superseded")
        self.assertIn(
            write.decision_record.decision_record_id,
            validity.superseded_decision_record_ids,
        )
        self.assertIsNone(validity.effective_decision_record_id)

    def test_duplicate_or_conflicting_decision_for_same_version_fails_closed(self) -> None:
        case, scenario = self._case_and_scenario()
        common = {
            "decision_case": case,
            "scenario": scenario,
            "reason": "First and only decision for this proposal version.",
            "actor_id": "owner@example.com",
            "actor_identity_class": "human",
            "engine": self.engine,
            "receipt_root": self.receipts,
        }
        record_planning_decision(decision="accepted_for_planning", **common)

        with self.assertRaisesRegex(ValueError, "already has DecisionRecord"):
            record_planning_decision(decision="rejected", **common)
        with Session(self.engine) as session:
            records = list(session.exec(select(DecisionRecord)).all())
        self.assertEqual(len(records), 1)

    def test_agent_requires_persisted_effective_delegated_review(self) -> None:
        case, scenario = self._case_and_scenario()
        with self.assertRaisesRegex(ValueError, "persisted delegated-review evidence"):
            record_planning_decision(
                decision_case=case,
                scenario=scenario,
                decision="accepted_for_planning",
                reason="Agent attempts to record without evidence.",
                actor_id="agent:capital",
                actor_identity_class="agent",
                engine=self.engine,
                receipt_root=self.receipts,
            )

        request = DelegatedReviewRequest(
            review_id="delegated_review_record_001",
            work_id="work_record_001",
            agent_id="agent:capital",
            decision_case_id=case.decision_case_id,
            decision_case_version_id=case.case_version_id,
            proposal_version_id=case.proposal_version.proposal_version_id,
            scenario_ids=(scenario.scenario_id,),
            selected_scenario_id=scenario.scenario_id,
            decision="accept_for_planning",
            rationale="The selected scenario is within the delegated mandate.",
            uncertainty=scenario.uncertainty,
            notional_implication=scenario.notional_implication,
        )
        result = evaluate_delegated_review(
            request=request,
            decision_case=case,
            scenarios=(scenario,),
            mandate=self._mandate(),
            runtime=aut3_runtime(world_state_ref=case.case_version_id),
        )
        review_ref = write_delegated_review_result(result, receipt_root=self.receipts)

        write = record_planning_decision(
            decision_case=case,
            scenario=scenario,
            decision="accepted_for_planning",
            reason="Record the mandate-contained delegated planning decision.",
            actor_id="agent:capital",
            actor_identity_class="agent",
            delegated_review_ref=review_ref,
            engine=self.engine,
            receipt_root=self.receipts,
        )
        self.assertEqual(write.validity.status, "effective")
        self.assertEqual(write.decision_record.delegated_review_ref, review_ref)

    def test_defer_requires_next_review_condition(self) -> None:
        case, _scenario = self._case_and_scenario()
        with self.assertRaisesRegex(ValueError, "next review condition"):
            record_planning_decision(
                decision_case=case,
                scenario=None,
                decision="deferred",
                reason="Evidence is not decisive yet.",
                actor_id="owner@example.com",
                actor_identity_class="human",
                engine=self.engine,
                receipt_root=self.receipts,
            )


if __name__ == "__main__":
    unittest.main()
