from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session

from finharness.api.app import create_app
from finharness.ips import record_ips
from finharness.statecore.models import (
    Account,
    ActionIntent,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
)
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core, read_all, write_records
from tests._scaffold import VALID_SCAFFOLD
from tests.asgi_test_client import AsgiTestClient


class ActionIntentCandidateApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
        )
        self.client = AsgiTestClient(self.app)
        self.proposal_write = create_governed_proposal(
            kind="rebalance_review",
            claim="Review whether a capital action should be considered.",
            evidence={"snapshot_id": "snap_after"},
            assumptions={"human_review": "required"},
            limitations={"execution": "none"},
            source_refs=["context://proposal"],
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id="prop_action_intent",
        )
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _request(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "action_type": "reduce_exposure",
            "intent_summary": "Consider reducing single-name exposure.",
            "rationale": "Reviewed proposal indicates concentration needs action planning.",
            "target_scope": {
                "scope_type": "single_instrument",
                "symbol": "XYZ",
                "account_scope": "portfolio_review",
            },
            "constraints": {"execution_mode": "none"},
            "trigger_context": {"source": "reviewed_proposal"},
            "required_preconditions": ["action_preflight"],
            "expected_next_step": "action_preflight",
            "expected_proposal_receipt_ref": self.proposal_write.receipt_ref,
            "source_refs": ["context://reviewed_proposal"],
        }
        payload.update(overrides)
        return payload

    def _create_intent(self, **overrides: object) -> dict[str, object]:
        response = self.client.post(
            f"/proposals/{self.proposal_write.proposal.proposal_id}/action-intents",
            json=self._request(**overrides),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["action_intent"]

    def _seed_portfolio_snapshot(self) -> None:
        account = Account(
            account_id="acct_action_preflight",
            kind="broker",
            venue="paper",
            display_name="Action Preflight Account",
            source_refs=["data/receipts/state-core/imports/receipt_account.json"],
        )
        snapshot = Snapshot(
            snapshot_id="snap_action_preflight",
            kind="portfolio",
            as_of_utc="2026-06-30T00:00:00+00:00",
            source_refs=["data/receipts/state-core/imports/receipt_snapshot.json"],
        )
        position = Position(
            position_id="pos_xyz",
            snapshot_id=snapshot.snapshot_id,
            account_id=account.account_id,
            symbol="XYZ",
            quantity=Decimal("10"),
            market_value=Decimal("1000"),
            source_refs=["data/receipts/state-core/imports/receipt_position.json"],
        )
        write_records([account, snapshot, position], engine=self.engine)

    def _seed_ips(self, *, restricted_actions: list[str] | None = None) -> None:
        record_ips(
            liquidity_floor_months=6,
            max_single_holding_pct="0.40",
            restricted_actions=restricted_actions or [],
            source_refs=["data/receipts/state-core/ips/receipt_policy_seed.json"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

    def _set_action_intent_fields(self, action_intent_id: str, **fields: object) -> None:
        with Session(self.engine) as session:
            action_intent = session.get(ActionIntent, action_intent_id)
            assert action_intent is not None
            for key, value in fields.items():
                setattr(action_intent, key, value)
            session.add(action_intent)
            session.commit()

    def test_create_action_intent_candidate_writes_receipt_and_can_be_fetched(self) -> None:
        response = self.client.post(
            f"/proposals/{self.proposal_write.proposal.proposal_id}/action-intents",
            json=self._request(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        self.assertIn("ActionIntentCandidate is not an order.", body["non_claims"])
        intent = body["action_intent"]
        self.assertEqual(intent["proposal_id"], self.proposal_write.proposal.proposal_id)
        self.assertEqual(intent["action_type"], "reduce_exposure")
        self.assertEqual(intent["status"], "candidate")
        self.assertEqual(intent["source_proposal_receipt_ref"], self.proposal_write.receipt_ref)
        self.assertFalse(intent["execution_allowed"])
        self.assertFalse(intent["authority_transition"])

        rows = read_all(ActionIntent, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].receipt_ref, body["receipt_ref"])
        receipts = read_all(ReceiptIndex, engine=self.engine)
        action_receipt = next(
            receipt
            for receipt in receipts
            if receipt.kind == "state_core_action_intent_candidate"
        )
        self.assertEqual(action_receipt.path, body["receipt_ref"])
        receipt_payload = json.loads(Path(body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt_payload["kind"], "state_core_action_intent_candidate")
        self.assertTrue(receipt_payload["governance"]["candidate_only"])
        self.assertTrue(receipt_payload["governance"]["not_order"])
        self.assertFalse(receipt_payload["governance"]["execution_allowed"])
        self.assertFalse(receipt_payload["governance"]["authority_transition"])

        fetched = self.client.get(f"/action-intents/{intent['action_intent_id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["action_intent"]["receipt_ref"], body["receipt_ref"])
        self.assertFalse(fetched.json()["execution_allowed"])

    def test_stale_proposal_receipt_is_rejected(self) -> None:
        response = self.client.post(
            f"/proposals/{self.proposal_write.proposal.proposal_id}/action-intents",
            json=self._request(expected_proposal_receipt_ref="data/receipts/stale.json"),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(read_all(ActionIntent, engine=self.engine), [])

    def test_missing_proposal_is_not_found(self) -> None:
        response = self.client.post(
            "/proposals/missing/action-intents",
            json=self._request(),
        )

        self.assertEqual(response.status_code, 404)

    def test_missing_rationale_or_summary_is_rejected(self) -> None:
        response = self.client.post(
            f"/proposals/{self.proposal_write.proposal.proposal_id}/action-intents",
            json=self._request(rationale=" "),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(ActionIntent, engine=self.engine), [])

    def test_order_and_broker_fields_are_rejected(self) -> None:
        for field, payload in (
            ("quantity", self._request(target_scope={"symbol": "XYZ", "quantity": 10})),
            ("broker", self._request(constraints={"broker": "alpaca"})),
            ("execution_allowed", self._request(trigger_context={"execution_allowed": True})),
            ("authority_transition", self._request(trigger_context={"authority_transition": True})),
            ("execution-allowed", self._request(trigger_context={"execution-allowed": True})),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    f"/proposals/{self.proposal_write.proposal.proposal_id}/action-intents",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(ActionIntent, engine=self.engine), [])

    def test_unknown_action_type_or_next_step_is_rejected(self) -> None:
        for field, payload in (
            ("action_type", self._request(action_type="market_order")),
            ("expected_next_step", self._request(expected_next_step="order_ticket")),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    f"/proposals/{self.proposal_write.proposal.proposal_id}/action-intents",
                    json=payload,
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(ActionIntent, engine=self.engine), [])

    def test_unknown_action_intent_is_not_found(self) -> None:
        response = self.client.get("/action-intents/missing")

        self.assertEqual(response.status_code, 404)

    def test_action_intent_preflight_passes_for_fresh_complete_intent(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent()

        first = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")
        second = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(first.status_code, 200)
        body = first.json()
        self.assertEqual(body["status"], "pass")
        self.assertTrue(body["system_preflight_recomputed"])
        self.assertEqual(body["freshness_status"], "fresh")
        self.assertEqual(body["target_scope_status"], "valid")
        self.assertEqual(body["policy_status"], "not_restricted")
        self.assertEqual(body["risk_posture"], "defensive")
        self.assertEqual(body["findings"], [])
        self.assertTrue(body["report_hash"].startswith("sha256:"))
        self.assertEqual(body["report_hash"], second.json()["report_hash"])
        self.assertIsNone(body["impact_summary"]["order_intent"])
        self.assertIsNone(body["impact_summary"]["notional_estimate"])
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])

    def test_action_intent_preflight_missing_ips_warns_without_blocking(self) -> None:
        self._seed_portfolio_snapshot()
        intent = self._create_intent()

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "warn")
        self.assertEqual(body["policy_status"], "unknown")
        self.assertIn("missing_current_ips", {finding["code"] for finding in body["findings"]})

    def test_action_intent_preflight_blocks_stale_source_proposal_receipt(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent()
        with Session(self.engine) as session:
            proposal = session.get(Proposal, self.proposal_write.proposal.proposal_id)
            assert proposal is not None
            proposal.receipt_ref = "data/receipts/state-core/proposals/receipt_newer.json"
            session.add(proposal)
            session.commit()

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertEqual(body["freshness_status"], "stale")
        self.assertIn(
            "stale_source_proposal_receipt",
            {finding["code"] for finding in body["findings"]},
        )

    def test_action_intent_preflight_blocks_missing_receipt_ref(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent()
        self._set_action_intent_fields(intent["action_intent_id"], receipt_ref=None)

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertIn(
            "missing_action_intent_receipt",
            {finding["code"] for finding in body["findings"]},
        )

    def test_action_intent_preflight_blocks_invalid_target_scope(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(target_scope={"symbol": "XYZ"})

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertEqual(body["target_scope_status"], "invalid")
        self.assertIn(
            "target_scope_missing_scope_type",
            {finding["code"] for finding in body["findings"]},
        )

    def test_action_intent_preflight_blocks_forbidden_nested_marker(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent()
        self._set_action_intent_fields(
            intent["action_intent_id"],
            constraints={"nested": {"execution-allowed": True}},
        )

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertIn(
            "forbidden_action_authority_marker",
            {finding["code"] for finding in body["findings"]},
        )

    def test_action_intent_preflight_blocks_ips_restricted_action(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips(restricted_actions=["reduce_exposure"])
        intent = self._create_intent()

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertEqual(body["policy_status"], "restricted")
        self.assertIn(
            "ips_restricted_action_type",
            {finding["code"] for finding in body["findings"]},
        )

    def test_action_intent_preflight_maps_evidence_only_posture(self) -> None:
        self._seed_ips()
        intent = self._create_intent(
            action_type="request_more_evidence",
            target_scope={"scope_type": "proposal"},
            intent_summary="Request more evidence before action planning.",
            rationale="The reviewed proposal needs more support.",
        )

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["risk_posture"], "evidence_only")
        self.assertEqual(body["impact_summary"]["risk_direction"], "evidence_only")

    def test_unknown_action_intent_preflight_is_not_found(self) -> None:
        response = self.client.get("/action-intents/missing/preflight")

        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
