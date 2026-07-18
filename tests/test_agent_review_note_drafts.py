from __future__ import annotations

import json
import unittest
from pathlib import Path

from finharness.agent_tools import (
    AGENT_REVIEW_NOTE_DRAFT_NON_CLAIMS,
    draft_agent_review_note_from_context_payload,
)
from finharness.review_read import read_proposal_timeline
from finharness.statecore.models import ReceiptIndex, ReviewEvent
from finharness.statecore.proposal_version import ProposalVersionResolutionError
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import read_all
from tests._scaffold import VALID_SCAFFOLD
from tests._statecore_fixtures import StateCoreFixture


class AgentReviewNoteDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = StateCoreFixture()
        self.engine = self.fixture.engine
        self.receipt_root = self.fixture.receipt_root
        self.addCleanup(self.fixture.cleanup)
        proposal = create_governed_proposal(
            kind="rebalance_review",
            claim="Review target allocation drift.",
            evidence={"drift_pct": 0.08},
            decision_scaffold=VALID_SCAFFOLD,
            source_refs=["context://capital_summary"],
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id="prop_review_note_target",
        )
        self.proposal_receipt_ref = proposal.receipt_ref

    def _draft(self, **overrides: object) -> dict[str, object]:
        payload = {
            "proposal_id": "prop_review_note_target",
            "review_kind": "risk_check",
            "suggested_severity": "medium",
            "summary": "Liquidity impact should be checked before human attestation.",
            "rationale": "The proposal evidence mentions drift but not cash timing.",
            "findings": ["Allocation drift evidence is present."],
            "risks": ["A rebalance could reduce near-term cash flexibility."],
            "open_questions": ["Is there a current cashflow context pack?"],
            "evidence_refs": ["evidence://drift"],
            "source_refs": ["context://proposal_timeline"],
            "context_pack_refs": ["context_pack://proposal_timeline"],
            "data_gaps": ["No current cashflow context pack cited."],
            "engine": self.engine,
            "receipt_root": self.receipt_root,
        }
        payload.update(overrides)
        return draft_agent_review_note_from_context_payload(**payload)  # type: ignore[arg-type]

    def test_rejects_profile_without_review_note_capability(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not allow capital-review-note"):
            self._draft(profile_name="default")

    def test_rejects_blank_proposal_id(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-blank proposal_id"):
            self._draft(proposal_id="  ")

    def test_rejects_empty_source_refs(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one source ref"):
            self._draft(source_refs=[])

    def test_rejects_unknown_review_kind_and_severity(self) -> None:
        with self.assertRaisesRegex(ValueError, "kind must be one of"):
            self._draft(review_kind="approve")
        with self.assertRaisesRegex(ValueError, "suggested_severity must be one of"):
            self._draft(suggested_severity="system_block")

    def test_rejects_authority_and_decision_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "execution_allowed"):
            self._draft(execution_allowed=True)
        with self.assertRaisesRegex(ValueError, "authority/decision"):
            self._draft(decision="approved")
        with self.assertRaisesRegex(ValueError, "authority/decision marker 'decision'"):
            self._draft(risks=[{"decision": "approved"}])

    def test_unknown_proposal_raises(self) -> None:
        with self.assertRaisesRegex(
            ProposalVersionResolutionError,
            "proposal not found",
        ):
            self._draft(proposal_id="missing")

    def test_creates_append_only_review_note_receipt_without_execution(self) -> None:
        body = self._draft()

        self.assertTrue(body["requires_human_review"])
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        self.assertEqual(body["profile_name"], "review-note")
        self.assertEqual(body["review_kind"], "risk_check")
        self.assertEqual(body["suggested_severity"], "medium")
        self.assertEqual(body["non_claims"], list(AGENT_REVIEW_NOTE_DRAFT_NON_CLAIMS))
        self.assertIn("receipt_ref", body)

        events = read_all(ReviewEvent, engine=self.engine)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.kind, "agent_review_note")
        self.assertEqual(event.attester, "agent:review-note")
        self.assertFalse(event.execution_allowed)
        self.assertIn(str(body["receipt_ref"]), event.source_refs)
        self.assertIn(self.proposal_receipt_ref, event.source_refs)

        note_payload = json.loads(event.text or "{}")
        self.assertEqual(note_payload["review_note_id"], body["review_note_id"])
        self.assertFalse(note_payload["transition_rule"]["may_approve"])
        self.assertFalse(note_payload["transition_rule"]["may_execute"])

        receipt_path = Path(str(body["receipt_ref"]))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["kind"], "state_core_review_event")
        self.assertEqual(receipt["review_event"]["kind"], "agent_review_note")
        self.assertFalse(receipt["governance"]["execution_allowed"])

        receipt_index = read_all(ReceiptIndex, engine=self.engine)
        review_receipts = [
            row for row in receipt_index if row.kind == "state_core_review_event"
        ]
        self.assertEqual(len(review_receipts), 1)
        self.assertIn("context://proposal_timeline", review_receipts[0].refs)

    def test_review_note_enters_proposal_timeline_as_typed_artifact(self) -> None:
        body = self._draft()

        timeline = read_proposal_timeline(self.engine, "prop_review_note_target")

        self.assertIsNotNone(timeline)
        entry = timeline.entries[0]  # type: ignore[union-attr]
        self.assertEqual(entry.source_type, "review_event")
        self.assertEqual(entry.kind, "agent_review_note")
        self.assertEqual(
            entry.detail["agent_review_note"]["review_note_id"],
            body["review_note_id"],
        )
        self.assertFalse(entry.detail["agent_review_note"]["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
