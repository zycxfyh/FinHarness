from __future__ import annotations

import json
import unittest
from pathlib import Path

from finharness.agent_tools import (
    AGENT_SCAFFOLD_REVISION_APPLY_CANDIDATE_NON_CLAIMS,
    draft_agent_scaffold_revision_apply_candidate_from_context_payload,
)
from finharness.review_read import read_proposal_timeline
from finharness.statecore.models import Proposal, ReceiptIndex, ReviewEvent
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import read_all
from tests._scaffold import VALID_SCAFFOLD
from tests._statecore_fixtures import StateCoreFixture


class AgentScaffoldRevisionApplyCandidateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = StateCoreFixture()
        self.engine = self.fixture.engine
        self.receipt_root = self.fixture.receipt_root
        self.addCleanup(self.fixture.cleanup)
        proposal = create_governed_proposal(
            kind="rebalance_review",
            claim="Review target allocation drift.",
            evidence={"data_gap": True},
            decision_scaffold=VALID_SCAFFOLD,
            source_refs=["context://capital_summary"],
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id="prop_scaffold_candidate_target",
        )
        self.proposal_receipt_ref = proposal.receipt_ref

    def _candidate(self, **overrides: object) -> dict[str, object]:
        payload = {
            "proposal_id": "prop_scaffold_candidate_target",
            "scaffold_patch": {
                "counter_evidence": (
                    "Liquidity and cashflow context are missing; human reviewer "
                    "should confirm them before apply."
                )
            },
            "change_summary": "Add counter-evidence prompt for missing liquidity context.",
            "rationale": "The risk register reports an unresolved evidence gap.",
            "basis_risk_ids": ["risk:prop_scaffold_candidate_target:evidence_gap"],
            "risk_coverage": {
                "addressed": ["risk:prop_scaffold_candidate_target:evidence_gap"],
                "unresolved": [],
            },
            "preflight_result": {
                "status": "candidate_only",
                "checks": ["scaffold_patch_shape", "basis_risk_exists"],
            },
            "rollback_info": {
                "previous_proposal_receipt_ref": self.proposal_receipt_ref,
                "apply_path": "human_confirmed_scaffold_revision",
            },
            "human_confirmation_requirements": [
                "Confirm changed_fields and source refs before applying.",
            ],
            "source_refs": ["context://risk_register"],
            "receipt_refs": [self.proposal_receipt_ref],
            "context_pack_refs": ["context_pack://risk_register"],
            "engine": self.engine,
            "receipt_root": self.receipt_root,
        }
        payload.update(overrides)
        return draft_agent_scaffold_revision_apply_candidate_from_context_payload(
            **payload
        )  # type: ignore[arg-type]

    def test_rejects_profile_without_scaffold_revision_capability(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not allow capital-scaffold-revision"):
            self._candidate(profile_name="default")

    def test_rejects_unknown_or_missing_basis_risks(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires basis_risk_ids"):
            self._candidate(basis_risk_ids=[])
        with self.assertRaisesRegex(ValueError, "unknown active risk"):
            self._candidate(basis_risk_ids=["risk:missing:evidence_gap"])

    def test_rejects_invalid_or_noop_scaffold_patch(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown field"):
            self._candidate(scaffold_patch={"unknown": "field"})
        with self.assertRaisesRegex(ValueError, "at least one changed field"):
            self._candidate(scaffold_patch={"decision_intent": VALID_SCAFFOLD["decision_intent"]})

    def test_rejects_nested_authority_markers(self) -> None:
        with self.assertRaisesRegex(ValueError, "authority/decision marker 'approval_status'"):
            self._candidate(preflight_result={"approval_status": "approved"})
        with self.assertRaisesRegex(ValueError, "authority/decision marker 'decision'"):
            self._candidate(risk_coverage={"nested": {"decision": "approve"}})

    def test_creates_append_only_apply_candidate_without_revising_proposal(self) -> None:
        body = self._candidate()

        self.assertTrue(body["apply_candidate"])
        self.assertEqual(body["consequence_class"], "C2")
        self.assertTrue(body["requires_human_review"])
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        self.assertEqual(body["profile_name"], "scaffold-candidate")
        self.assertEqual(
            body["non_claims"],
            list(AGENT_SCAFFOLD_REVISION_APPLY_CANDIDATE_NON_CLAIMS),
        )
        self.assertEqual(body["changed_fields"], ["counter_evidence"])
        self.assertIn("counter_evidence", body["proposed_scaffold"])

        proposals = {
            row.proposal_id: row for row in read_all(Proposal, engine=self.engine)
        }
        self.assertNotIn(
            "counter_evidence",
            proposals["prop_scaffold_candidate_target"].decision_scaffold,
        )

        events = read_all(ReviewEvent, engine=self.engine)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.kind, "agent_scaffold_revision_apply_candidate")
        self.assertEqual(event.attester, "agent:scaffold-candidate")
        self.assertFalse(event.execution_allowed)
        self.assertIn(str(body["receipt_ref"]), event.source_refs)
        self.assertIn(self.proposal_receipt_ref, event.source_refs)
        self.assertIn("risk:prop_scaffold_candidate_target:evidence_gap", event.source_refs)

        payload = json.loads(event.text or "{}")
        self.assertEqual(payload["candidate_id"], body["candidate_id"])
        self.assertTrue(payload["transition_rule"]["may_be_applied_by_human_confirmed_flow"])
        self.assertFalse(
            payload["transition_rule"]["may_revise_proposal_without_human_confirmation"]
        )
        self.assertFalse(payload["transition_rule"]["may_execute"])

        receipt = json.loads(Path(str(body["receipt_ref"])).read_text(encoding="utf-8"))
        self.assertEqual(receipt["kind"], "state_core_review_event")
        self.assertEqual(
            receipt["review_event"]["kind"],
            "agent_scaffold_revision_apply_candidate",
        )
        self.assertFalse(receipt["governance"]["execution_allowed"])

        receipt_index = read_all(ReceiptIndex, engine=self.engine)
        review_receipts = [
            row for row in receipt_index if row.kind == "state_core_review_event"
        ]
        self.assertEqual(len(review_receipts), 1)
        self.assertIn("context://risk_register", review_receipts[0].refs)

    def test_candidate_enters_proposal_timeline_as_typed_artifact(self) -> None:
        body = self._candidate()

        timeline = read_proposal_timeline(
            self.engine,
            "prop_scaffold_candidate_target",
        )

        self.assertIsNotNone(timeline)
        entry = timeline.entries[0]  # type: ignore[union-attr]
        self.assertEqual(entry.source_type, "review_event")
        self.assertEqual(entry.kind, "agent_scaffold_revision_apply_candidate")
        self.assertEqual(
            entry.detail["agent_scaffold_revision_apply_candidate"]["candidate_id"],
            body["candidate_id"],
        )
        self.assertFalse(
            entry.detail["agent_scaffold_revision_apply_candidate"]["execution_allowed"]
        )


if __name__ == "__main__":
    unittest.main()
