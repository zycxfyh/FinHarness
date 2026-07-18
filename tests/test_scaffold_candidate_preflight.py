from __future__ import annotations

import json
import unittest

from sqlmodel import Session, select

from finharness.agent_tools import (
    draft_agent_scaffold_revision_apply_candidate_from_context_payload,
)
from finharness.api.app import create_app
from finharness.scaffold_candidate_preflight import (
    preflight_scaffold_revision_candidate,
)
from finharness.statecore.models import ReviewEvent
from finharness.statecore.proposals import (
    create_governed_proposal,
    revise_governed_proposal_scaffold,
)
from tests._scaffold import VALID_SCAFFOLD
from tests._statecore_fixtures import StateCoreFixture
from tests.asgi_test_client import AsgiTestClient


class ScaffoldRevisionCandidatePreflightTest(unittest.TestCase):
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
            proposal_id="prop_candidate_preflight_target",
        )
        self.proposal_receipt_ref = proposal.receipt_ref
        self.candidate = draft_agent_scaffold_revision_apply_candidate_from_context_payload(
            proposal_id="prop_candidate_preflight_target",
            scaffold_patch={
                "counter_evidence": (
                    "Liquidity and tax context must be checked before human approval."
                )
            },
            change_summary="Add counter-evidence to cover the evidence gap.",
            rationale="Risk register reports unresolved evidence.",
            basis_risk_ids=["risk:prop_candidate_preflight_target:evidence_gap"],
            risk_coverage={
                "addressed": ["risk:prop_candidate_preflight_target:evidence_gap"],
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

    def _candidate_event(self) -> ReviewEvent:
        with Session(self.engine) as session:
            return session.exec(
                select(ReviewEvent).where(
                    ReviewEvent.review_event_id
                    == str(self.candidate["review_event_id"])
                )
            ).one()

    def _replace_candidate_payload(self, payload_text: str) -> None:
        with Session(self.engine) as session:
            event = session.get(ReviewEvent, str(self.candidate["review_event_id"]))
            self.assertIsNotNone(event)
            event.text = payload_text  # type: ignore[union-attr]
            session.add(event)
            session.commit()

    def _candidate_payload(self) -> dict[str, object]:
        event = self._candidate_event()
        payload = json.loads(event.text or "{}")
        self.assertIsInstance(payload, dict)
        return payload

    def _replace_candidate_json_payload(self, payload: dict[str, object]) -> None:
        self._replace_candidate_payload(json.dumps(payload, sort_keys=True))

    def test_system_preflight_passes_for_current_candidate(self) -> None:
        report = preflight_scaffold_revision_candidate(
            str(self.candidate["candidate_id"]),
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

        self.assertIsNotNone(report)
        self.assertEqual(report.status, "pass")  # type: ignore[union-attr]
        self.assertTrue(report.system_preflight_recomputed)  # type: ignore[union-attr]
        self.assertEqual(report.findings, [])  # type: ignore[union-attr]
        self.assertEqual(report.changed_fields, ["counter_evidence"])  # type: ignore[union-attr]
        self.assertEqual(
            report.active_basis_risk_ids,  # type: ignore[union-attr]
            ["risk:prop_candidate_preflight_target:evidence_gap"],
        )
        self.assertEqual(report.missing_basis_risk_ids, [])  # type: ignore[union-attr]
        self.assertEqual(report.candidate_receipt_ref, self.candidate["receipt_ref"])  # type: ignore[union-attr]
        self.assertEqual(report.current_proposal_receipt_ref, self.proposal_receipt_ref)  # type: ignore[union-attr]
        self.assertTrue(report.report_hash.startswith("sha256:"))  # type: ignore[union-attr]
        self.assertFalse(report.execution_allowed)  # type: ignore[union-attr]
        self.assertFalse(report.authority_transition)  # type: ignore[union-attr]

    def test_get_preflight_endpoint_is_read_only_and_non_authoritative(self) -> None:
        response = self.client.get(
            f"/scaffold-revision-candidates/{self.candidate['candidate_id']}/preflight"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "pass")
        self.assertTrue(body["system_preflight_recomputed"])
        self.assertEqual(body["findings"], [])
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        self.assertIn("not approval", " ".join(body["non_claims"]).lower())

    def test_preflight_blocks_stale_proposal_receipt(self) -> None:
        expectation = self.fixture._version_expectation(
            "prop_candidate_preflight_target"
        )
        revise_governed_proposal_scaffold(
            proposal_id="prop_candidate_preflight_target",
            scaffold_patch={"alternatives": "Wait for updated cashflow context."},
            attester="Jane Control",
            reason="Human reviewer added an alternative before candidate apply.",
            source_refs=["human://review"],
            expectation=expectation,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

        response = self.client.get(
            f"/scaffold-revision-candidates/{self.candidate['candidate_id']}/preflight"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        codes = {finding["code"] for finding in body["findings"]}
        self.assertIn("stale_proposal_receipt", codes)
        self.assertIn("candidate_proposed_scaffold_mismatch", codes)

    def test_preflight_blocks_candidate_scaffold_mismatch(self) -> None:
        payload = self._candidate_payload()
        payload["proposed_scaffold"]["counter_evidence"] = "Agent payload drifted."
        self._replace_candidate_json_payload(payload)

        response = self.client.get(
            f"/scaffold-revision-candidates/{self.candidate['candidate_id']}/preflight"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertIn(
            "candidate_proposed_scaffold_mismatch",
            {finding["code"] for finding in body["findings"]},
        )

    def test_preflight_blocks_inactive_or_unrelated_basis_risks(self) -> None:
        payload = self._candidate_payload()
        payload["basis_risk_ids"] = ["risk:missing:evidence_gap"]
        payload["risk_coverage"] = {
            "addressed": ["risk:missing:evidence_gap"],
            "unresolved": [],
        }
        self._replace_candidate_json_payload(payload)

        response = self.client.get(
            f"/scaffold-revision-candidates/{self.candidate['candidate_id']}/preflight"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertEqual(body["active_basis_risk_ids"], [])
        self.assertEqual(body["missing_basis_risk_ids"], ["risk:missing:evidence_gap"])
        finding = {
            item["code"]: item
            for item in body["findings"]
        }["inactive_or_unrelated_basis_risks"]
        self.assertTrue(finding["blocks_apply"])
        self.assertEqual(finding["severity"], "blocking")

    def test_preflight_warns_when_risk_coverage_is_incomplete_without_blocking(self) -> None:
        payload = self._candidate_payload()
        payload["risk_coverage"] = {"addressed": [], "unresolved": []}
        self._replace_candidate_json_payload(payload)

        response = self.client.get(
            f"/scaffold-revision-candidates/{self.candidate['candidate_id']}/preflight"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "warn")
        finding = {
            item["code"]: item
            for item in body["findings"]
        }["risk_coverage_incomplete"]
        self.assertEqual(finding["severity"], "warning")
        self.assertFalse(finding["blocks_apply"])
        self.assertEqual(body["missing_basis_risk_ids"], [])

    def test_preflight_blocks_forbidden_authority_marker(self) -> None:
        payload = self._candidate_payload()
        payload["risk_coverage"] = {
            "addressed": ["risk:prop_candidate_preflight_target:evidence_gap"],
            "nested": {"approval_status": "approved"},
        }
        self._replace_candidate_json_payload(payload)

        response = self.client.get(
            f"/scaffold-revision-candidates/{self.candidate['candidate_id']}/preflight"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        finding = {
            item["code"]: item
            for item in body["findings"]
        }["forbidden_authority_marker"]
        self.assertTrue(finding["blocks_apply"])
        self.assertIn("approval_status", finding["message"])

    def test_preflight_blocks_unreadable_candidate_payload(self) -> None:
        self._replace_candidate_payload(
            '{"candidate_id": "' + str(self.candidate["candidate_id"]) + '",'
        )

        response = self.client.get(
            f"/scaffold-revision-candidates/{self.candidate['candidate_id']}/preflight"
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertEqual(body["findings"][0]["code"], "candidate_payload_unreadable")
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])

    def test_preflight_unknown_candidate_returns_404(self) -> None:
        response = self.client.get("/scaffold-revision-candidates/missing/preflight")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
