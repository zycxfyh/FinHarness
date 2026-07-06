from __future__ import annotations

import json
import unittest
from pathlib import Path

from finharness.agent_context import (
    build_open_proposals_context,
    build_proposal_timeline_context,
)
from finharness.agent_tools import (
    AGENT_PROPOSAL_DRAFT_NON_CLAIMS,
    draft_governed_proposal_from_context_payload,
)
from finharness.api.app import create_app
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.models import Attestation, Proposal
from finharness.statecore.proposals import create_governed_attestation
from finharness.statecore.risk_classification import HighRiskConfirmationError
from finharness.statecore.store import read_all
from tests._scaffold import VALID_SCAFFOLD
from tests._statecore_fixtures import StateCoreFixture
from tests.asgi_test_client import AsgiTestClient


class AgentProposalDraftTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = StateCoreFixture()
        self.engine = self.fixture.engine
        self.receipt_root = self.fixture.receipt_root
        self.addCleanup(self.fixture.cleanup)

    def _draft(self, **overrides: object) -> dict[str, object]:
        payload = {
            "kind": "cash_buffer_low",
            "claim": "Review the cash buffer because runway is below policy.",
            "evidence": {"runway_months": 2.0},
            "decision_scaffold": VALID_SCAFFOLD,
            "source_refs": ["context://capital_summary"],
            "reason": "Agent surfaced a review draft from bounded context.",
            "engine": self.engine,
            "receipt_root": self.receipt_root,
        }
        payload.update(overrides)
        return draft_governed_proposal_from_context_payload(**payload)  # type: ignore[arg-type]

    def test_rejects_blank_claim(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-blank claim"):
            self._draft(claim="   ")

    def test_rejects_blank_reason(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-blank reason"):
            self._draft(reason="   ")

    def test_rejects_empty_source_refs(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one source ref"):
            self._draft(source_refs=[])

    def test_rejects_direct_execution_kind(self) -> None:
        for kind in ("execute_order", "fund_transfer", "broker_trade", "action_intent"):
            with self.subTest(kind=kind), self.assertRaisesRegex(
                ValueError, "execution/order/transfer"
            ):
                self._draft(kind=kind)

    def test_allows_normal_finance_review_kind_terms_without_substring_blocks(
        self,
    ) -> None:
        for kind in (
            "emergency_fund_review",
            "funding_gap_review",
            "tradeoff_review",
            "brokerage_fee_review",
            "orderly_rebalance_review",
        ):
            with self.subTest(kind=kind):
                body = self._draft(kind=kind)
                self.assertEqual(body["kind"], kind)

    def test_rejects_execution_allowed_attempts(self) -> None:
        with self.assertRaisesRegex(ValueError, "execution_allowed=true"):
            self._draft(evidence={"execution_allowed": True})
        with self.assertRaisesRegex(ValueError, "execution_allowed=true"):
            self._draft(decision_scaffold={**VALID_SCAFFOLD, "execution_allowed": True})

    def test_rejects_profile_without_capital_propose(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not allow capital-propose"):
            self._draft(profile_name="default")

    def test_creates_governed_proposal_receipt_without_execution(self) -> None:
        body = self._draft()

        self.assertTrue(body["requires_human_review"])
        self.assertFalse(body["execution_allowed"])
        self.assertEqual(body["authority_level"], "needs_human_confirm")
        self.assertEqual(body["non_claims"], list(AGENT_PROPOSAL_DRAFT_NON_CLAIMS))
        self.assertEqual(body["source_refs"], ["context://capital_summary"])

        proposals = read_all(Proposal, engine=self.engine)
        self.assertEqual(len(proposals), 1)
        self.assertFalse(proposals[0].execution_allowed)

        receipt_path = Path(str(body["receipt_ref"]))
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertFalse(payload["governance"]["execution_allowed"])
        self.assertTrue(payload["governance"]["human_review_required"])
        self.assertEqual(payload["revision_context"]["kind"], "agent_proposal_draft")
        self.assertEqual(payload["revision_context"]["profile"], "review-draft")

    def test_created_proposal_appears_in_open_context(self) -> None:
        body = self._draft()

        context = build_open_proposals_context(self.engine).model_dump(mode="json")

        self.assertTrue(context["available"])
        self.assertIn(
            body["proposal_id"],
            {item["proposal_id"] for item in context["summary"]["items"]},
        )

    def test_created_proposal_timeline_context_is_readable(self) -> None:
        body = self._draft()

        context = build_proposal_timeline_context(
            self.engine,
            str(body["proposal_id"]),
        ).model_dump(mode="json")

        self.assertTrue(context["available"])
        self.assertEqual(context["summary"]["proposal_id"], body["proposal_id"])
        self.assertEqual(context["summary"]["entry_count"], 0)
        self.assertFalse(context["execution_allowed"])

    def test_api_review_surface_exposes_agent_draft_provenance(self) -> None:
        body = self._draft(context_pack_refs=["context://capital_summary"])
        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)

        detail = client.get(f"/proposals/{body['proposal_id']}").json()
        listed = client.get("/proposals", params={"status": "open"}).json()

        agent_review = detail["agent_review"]
        self.assertEqual(agent_review["created_by"], "agent")
        self.assertEqual(agent_review["active_profile"], "review-draft")
        self.assertEqual(agent_review["context_pack_refs"], ["context://capital_summary"])
        self.assertEqual(agent_review["source_refs"], ["context://capital_summary"])
        self.assertEqual(agent_review["receipt_ref"], body["receipt_ref"])
        self.assertEqual(agent_review["review_state"], "pending_human_review")
        self.assertTrue(agent_review["requires_human_review"])
        self.assertFalse(agent_review["execution_allowed"])
        self.assertFalse(agent_review["authority_transition"])
        self.assertTrue(agent_review["guardrails"]["not_attestation"])
        self.assertIn("not approval", " ".join(agent_review["non_claims"]).lower())
        self.assertEqual(listed[0]["agent_review"]["created_by"], "agent")

        queue_checks = detail["queue_checks"]
        self.assertEqual(queue_checks["created_by"], "agent")
        self.assertEqual(queue_checks["active_profile"], "review-draft")
        self.assertEqual(queue_checks["check_state"], "block")
        self.assertEqual(queue_checks["source_refs"], body["source_refs"])
        self.assertEqual(queue_checks["context_pack_refs"], ["context://capital_summary"])
        self.assertFalse(queue_checks["execution_allowed"])
        self.assertFalse(queue_checks["authority_transition"])
        self.assertEqual(
            queue_checks["blocked_transitions"],
            ["human_attestation", "authority_transition", "execution"],
        )
        human_review_block = next(
            item
            for item in queue_checks["blocks"]
            if item["code"] == "human_review_required"
        )
        self.assertEqual(
            human_review_block["blocked_transitions"],
            ["human_attestation", "authority_transition", "execution"],
        )
        self.assertNotIn("review_entry", human_review_block["blocked_transitions"])
        self.assertEqual(listed[0]["queue_checks"]["created_by"], "agent")

        explicit = client.get(f"/proposals/{body['proposal_id']}/queue-checks").json()
        self.assertEqual(explicit, queue_checks)

    def test_api_review_surface_keeps_agent_source_refs_from_draft_receipt(self) -> None:
        body = self._draft(
            context_pack_refs=["context://capital_summary"],
            source_refs=["context://agent_source"],
        )
        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)

        revised = client.patch(
            f"/proposals/{body['proposal_id']}/decision-scaffold",
            json={
                "attester": "Jane Control",
                "reason": "Added human review source after Agent draft.",
                "decision_scaffold": {
                    "counter_evidence": (
                        "If updated cash runway exceeds six months, the review should pause."
                    )
                },
                "source_refs": ["human://review_note"],
            },
        )
        self.assertEqual(revised.status_code, 200)
        self.assertIn("human://review_note", revised.json()["proposal"]["source_refs"])

        detail = client.get(f"/proposals/{body['proposal_id']}").json()

        agent_review = detail["agent_review"]
        self.assertEqual(agent_review["receipt_ref"], body["receipt_ref"])
        self.assertEqual(agent_review["source_refs"], body["source_refs"])
        self.assertNotIn("human://review_note", agent_review["source_refs"])

    def test_agent_queue_checks_report_duplicate_open_drafts(self) -> None:
        first = self._draft()
        second = self._draft()
        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)

        checks = client.get(f"/proposals/{second['proposal_id']}/queue-checks").json()

        duplicate_blocks = [
            item for item in checks["blocks"] if item["code"] == "duplicate_proposal"
        ]
        self.assertEqual(checks["check_state"], "block")
        self.assertIn("review_entry", checks["blocked_transitions"])
        self.assertEqual(len(duplicate_blocks), 1)
        self.assertIn("review_entry", duplicate_blocks[0]["blocked_transitions"])
        self.assertIn(first["proposal_id"], duplicate_blocks[0]["related_proposal_ids"])

    def test_agent_queue_checks_clear_human_review_required_after_attestation(self) -> None:
        body = self._draft()
        create_governed_attestation(
            proposal_id=str(body["proposal_id"]),
            decision="rejected",
            attester="Jane Control",
            reason="Recorded human review; this is not execution authorization.",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)

        checks = client.get(f"/proposals/{body['proposal_id']}/queue-checks").json()

        self.assertEqual(checks["check_state"], "pass")
        self.assertFalse(checks["open_for_review"])
        self.assertEqual(checks["blocked_transitions"], [])
        self.assertNotIn("human_review_required", {item["code"] for item in checks["blocks"]})
        self.assertFalse(checks["execution_allowed"])
        self.assertFalse(checks["authority_transition"])

    def test_high_risk_draft_cannot_bypass_counter_evidence_approval_gate(self) -> None:
        body = self._draft(
            kind="concentration_high",
            claim="Review concentration above the user's threshold.",
            evidence={"top_holding_weight": 0.8},
        )

        with self.assertRaises(HighRiskConfirmationError):
            create_governed_attestation(
                proposal_id=str(body["proposal_id"]),
                decision="approved",
                attester="Jane Control",
                reason="Attempted approval before counter-evidence.",
                engine=self.engine,
                receipt_root=self.receipt_root,
            )
        self.assertEqual(read_all(Attestation, engine=self.engine), [])

        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)
        checks = client.get(f"/proposals/{body['proposal_id']}/queue-checks").json()
        counter_evidence_block = next(
            item
            for item in checks["blocks"]
            if item["code"] == "counter_evidence_needed"
        )
        self.assertEqual(
            counter_evidence_block["blocked_transitions"],
            ["human_attestation", "authority_transition", "execution"],
        )


if __name__ == "__main__":
    unittest.main()
