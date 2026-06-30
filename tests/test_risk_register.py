from __future__ import annotations

import unittest

from finharness.agent_tools import draft_agent_review_note_from_context_payload
from finharness.api.app import create_app
from finharness.risk_register import read_review_risk_register
from tests._review_fixtures import ReviewFixture
from tests.asgi_test_client import AsgiTestClient


class RiskRegisterReadModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = ReviewFixture()
        self.addCleanup(self.fx.cleanup)

    def test_agent_review_note_data_gap_becomes_evidence_gap_risk(self) -> None:
        self.fx.proposal("gap_target", source_refs=["context://proposal"])
        draft_agent_review_note_from_context_payload(
            proposal_id="gap_target",
            review_kind="risk_check",
            suggested_severity="high",
            summary="Liquidity evidence needs a second look.",
            rationale="The proposal does not show near-term cash timing.",
            findings=["Drift evidence exists."],
            risks=["Cash timing could change the review outcome."],
            open_questions=["Is the latest cashflow context current?"],
            evidence_refs=["evidence://drift"],
            source_refs=["context://proposal_timeline"],
            context_pack_refs=["context_pack://proposal_timeline"],
            data_gaps=["No cashflow context pack cited."],
            engine=self.fx.engine,
            receipt_root=self.fx.receipt_root,
        )

        register = read_review_risk_register(
            self.fx.engine,
            receipt_root=self.fx.receipt_root,
        )
        by_kind = {item.risk_kind: item for item in register.items}

        evidence_gap = by_kind["evidence_gap"]
        self.assertEqual(evidence_gap.risk_id, "risk:gap_target:evidence_gap")
        self.assertEqual(evidence_gap.status, "open")
        self.assertEqual(evidence_gap.severity_hint, "high")
        self.assertEqual(evidence_gap.data_gaps, ["No cashflow context pack cited."])
        self.assertEqual(
            evidence_gap.source_refs,
            [
                "context://proposal",
                "context://proposal_timeline",
                "evidence://drift",
            ],
        )
        self.assertFalse(evidence_gap.execution_allowed)
        self.assertFalse(evidence_gap.authority_transition)

        agent_risk = by_kind["agent_reported_risk"]
        self.assertEqual(
            agent_risk.risk_reasons,
            ["Cash timing could change the review outcome."],
        )
        self.assertIn("open_question", by_kind)

    def test_stale_context_and_duplicate_candidates_become_risk_items(self) -> None:
        self.fx.proposal(
            "stale",
            evidence={"stale_context": True},
            source_refs=["context://old"],
        )
        self.fx.proposal(
            "dup_a",
            kind="rebalance_review",
            claim="Review the same target allocation.",
            source_refs=["context://dup"],
        )
        self.fx.proposal(
            "dup_b",
            kind="rebalance_review",
            claim="Review the same target allocation.",
            source_refs=["context://dup"],
        )

        register = read_review_risk_register(
            self.fx.engine,
            receipt_root=self.fx.receipt_root,
        )
        by_id = {item.risk_id: item for item in register.items}

        stale = by_id["risk:stale:stale_context"]
        self.assertEqual(stale.risk_kind, "stale_context")
        self.assertEqual(stale.evidence_status, "needs_context")
        self.assertTrue(stale.data_gaps)

        duplicate = by_id["risk:dup_a:duplicate_proposal"]
        self.assertEqual(
            duplicate.related_proposal_ids,
            ["dup_a", "dup_b"],
        )
        self.assertIn(
            "compare duplicate candidates before progressing review",
            duplicate.next_actions,
        )
        self.assertFalse(duplicate.execution_allowed)

    def test_closed_proposals_are_excluded_by_default_and_included_when_requested(self) -> None:
        self.fx.proposal("active", evidence={"data_gap": True}, source_refs=["context://active"])
        self.fx.proposal(
            "attested",
            evidence={"data_gap": True},
            source_refs=["context://attested"],
        )
        self.fx.attest("attested")

        active = read_review_risk_register(
            self.fx.engine,
            receipt_root=self.fx.receipt_root,
        )
        self.assertEqual({item.related_proposal_ids[0] for item in active.items}, {"active"})

        all_items = read_review_risk_register(
            self.fx.engine,
            receipt_root=self.fx.receipt_root,
            include_closed=True,
        )
        statuses = {item.related_proposal_ids[0]: item.status for item in all_items.items}
        self.assertEqual(statuses["active"], "open")
        self.assertEqual(statuses["attested"], "reviewed")


class RiskRegisterApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = ReviewFixture()
        self.app = create_app(
            state_core_engine=self.fx.engine,
            receipt_root=str(self.fx.receipt_root),
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.fx.cleanup)

    def test_get_risk_register_is_read_only_and_non_authoritative(self) -> None:
        self.fx.proposal("api_target", source_refs=["context://proposal"])
        draft_agent_review_note_from_context_payload(
            proposal_id="api_target",
            review_kind="risk_check",
            suggested_severity="high",
            summary="Review the cash timing evidence.",
            rationale="The proposal does not cite a cashflow context pack.",
            findings=["Proposal source refs are present."],
            risks=["Cash timing could change the review outcome."],
            open_questions=["Is the cashflow context current?"],
            evidence_refs=["evidence://cashflow"],
            source_refs=["context://proposal_timeline"],
            context_pack_refs=["context_pack://proposal_timeline"],
            data_gaps=["No cashflow context pack cited."],
            engine=self.fx.engine,
            receipt_root=self.fx.receipt_root,
        )

        body = self.client.get("/risk/register").json()

        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        self.assertIn("not investment advice", " ".join(body["non_claims"]))
        kinds = {item["risk_kind"] for item in body["items"]}
        self.assertIn("evidence_gap", kinds)
        self.assertIn("agent_reported_risk", kinds)
        for item in body["items"]:
            self.assertFalse(item["execution_allowed"])
            self.assertFalse(item["authority_transition"])
            self.assertEqual(item["source_type"], "review_queue")


if __name__ == "__main__":
    unittest.main()
