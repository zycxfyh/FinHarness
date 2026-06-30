from __future__ import annotations

import json
import unittest
from pathlib import Path

from finharness.agent_tools import (
    draft_agent_scaffold_revision_apply_candidate_from_context_payload,
)
from finharness.api.app import create_app
from finharness.statecore.models import Proposal
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import read_all
from tests._scaffold import VALID_SCAFFOLD
from tests._statecore_fixtures import StateCoreFixture
from tests.asgi_test_client import AsgiTestClient


class ScaffoldRevisionCandidateApplyApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = StateCoreFixture()
        self.engine = self.fixture.engine
        self.receipt_root = self.fixture.receipt_root
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.fixture.cleanup)
        proposal = create_governed_proposal(
            kind="rebalance_review",
            claim="Review target allocation drift.",
            evidence={"data_gap": True},
            decision_scaffold=VALID_SCAFFOLD,
            source_refs=["context://capital_summary"],
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id="prop_candidate_apply_target",
        )
        self.proposal_receipt_ref = proposal.receipt_ref
        self.candidate = draft_agent_scaffold_revision_apply_candidate_from_context_payload(
            proposal_id="prop_candidate_apply_target",
            scaffold_patch={
                "counter_evidence": (
                    "Liquidity and tax context must be checked before human approval."
                )
            },
            change_summary="Add counter-evidence to cover the evidence gap.",
            rationale="Risk register reports unresolved evidence.",
            basis_risk_ids=["risk:prop_candidate_apply_target:evidence_gap"],
            risk_coverage={
                "addressed": ["risk:prop_candidate_apply_target:evidence_gap"],
                "unresolved": [],
            },
            preflight_result={"status": "candidate_only"},
            rollback_info={"previous_proposal_receipt_ref": self.proposal_receipt_ref},
            human_confirmation_requirements=[
                "Confirm expected candidate and proposal receipts before applying.",
            ],
            source_refs=["context://risk_register"],
            receipt_refs=[self.proposal_receipt_ref],
            context_pack_refs=["context_pack://risk_register"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

    def _apply(self, **overrides: object):
        body = {
            "human_attester": "Jane Control",
            "human_reason": "Confirmed the candidate patch addresses the evidence gap.",
            "expected_candidate_receipt_ref": self.candidate["receipt_ref"],
            "expected_proposal_receipt_ref": self.proposal_receipt_ref,
            "explicit_confirmation": True,
        }
        body.update(overrides)
        return self.client.post(
            f"/scaffold-revision-candidates/{self.candidate['candidate_id']}/apply",
            json=body,
        )

    def test_human_confirmed_apply_revises_scaffold_and_links_candidate_receipt(self) -> None:
        response = self._apply()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        self.assertEqual(body["applied_candidate_id"], self.candidate["candidate_id"])
        self.assertEqual(body["candidate_receipt_ref"], self.candidate["receipt_ref"])
        self.assertEqual(body["previous_receipt_ref"], self.proposal_receipt_ref)
        self.assertEqual(body["changed_scaffold_fields"], ["counter_evidence"])
        self.assertEqual(
            body["proposal"]["decision_scaffold"]["counter_evidence"],
            "Liquidity and tax context must be checked before human approval.",
        )

        proposals = {
            row.proposal_id: row for row in read_all(Proposal, engine=self.engine)
        }
        self.assertEqual(
            proposals["prop_candidate_apply_target"].decision_scaffold["counter_evidence"],
            "Liquidity and tax context must be checked before human approval.",
        )

        receipt = json.loads(Path(body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt["supersedes"], self.proposal_receipt_ref)
        context = receipt["revision_context"]
        self.assertEqual(context["kind"], "decision_scaffold_revision")
        self.assertEqual(context["source"], "agent_scaffold_revision_apply_candidate")
        self.assertEqual(context["candidate_id"], self.candidate["candidate_id"])
        self.assertEqual(context["candidate_receipt_ref"], self.candidate["receipt_ref"])
        self.assertTrue(context["human_confirmed"])
        self.assertFalse(context["execution_allowed"])

    def test_apply_requires_explicit_confirmation(self) -> None:
        response = self._apply(explicit_confirmation=False)

        self.assertEqual(response.status_code, 422)
        self.assertIn("explicit_confirmation", response.text)

    def test_apply_rejects_stale_candidate_or_proposal_receipt(self) -> None:
        stale_candidate = self._apply(expected_candidate_receipt_ref="receipt://stale")
        stale_proposal = self._apply(expected_proposal_receipt_ref="receipt://stale")

        self.assertEqual(stale_candidate.status_code, 409)
        self.assertIn("candidate receipt ref", stale_candidate.json()["detail"])
        self.assertEqual(stale_proposal.status_code, 409)
        self.assertIn("proposal receipt ref", stale_proposal.json()["detail"])

    def test_apply_unknown_candidate_returns_404(self) -> None:
        response = self.client.post(
            "/scaffold-revision-candidates/missing/apply",
            json={
                "human_attester": "Jane Control",
                "human_reason": "Trying a missing candidate.",
                "expected_candidate_receipt_ref": "receipt://missing",
                "expected_proposal_receipt_ref": self.proposal_receipt_ref,
                "explicit_confirmation": True,
            },
        )

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
