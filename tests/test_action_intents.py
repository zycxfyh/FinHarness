from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session

from finharness.api.app import create_app
from finharness.ips import record_ips
from finharness.statecore.action_intent_authority_bindings import (
    create_action_intent_authority_binding,
)
from finharness.statecore.agent_authority_grants import record_agent_authority_grant
from finharness.statecore.capital_mandates import record_capital_mandate
from finharness.statecore.models import (
    Account,
    ActionIntent,
    ActionIntentSimulationReport,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
    TradePlanCandidate,
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

    def _authority_scope(self, *, action: str = "reduce_exposure") -> dict[str, object]:
        return {
            "allowed_asset_classes": ["cash", "equity"],
            "allowed_action_types": [action],
            "autonomy_level": "L1_candidate_only",
        }

    def _record_mandate(self, *, mandate_id: str = "mandate_action_preflight") -> str:
        mandate = record_capital_mandate(
            capital_mandate_id=mandate_id,
            profile_snapshot={"profile": "balanced"},
            investment_objectives={"primary": "risk_control"},
            risk_profile={"max_drawdown_pct": 0.10},
            allowed_asset_classes=["cash", "equity"],
            restricted_asset_classes=["crypto_leverage"],
            allowed_action_types=["reduce_exposure", "rebalance", "raise_cash"],
            restricted_action_types=["open_margin"],
            autonomy_level="L1_candidate_only",
            human_attester="owner@example.com",
            human_reason="Attest mandate scope for action preflight tests.",
            explicit_confirmation=True,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        return mandate.capital_mandate_id

    def _record_grant(
        self,
        *,
        grant_id: str = "grant_action_preflight",
        action: str = "reduce_exposure",
        agent_id: str = "agent:research",
    ) -> str:
        grant = record_agent_authority_grant(
            agent_authority_grant_id=grant_id,
            capital_mandate_id=self._record_mandate(),
            agent_id=agent_id,
            agent_profile_name="review-note",
            grant_scope=self._authority_scope(action=action),
            issued_by="owner@example.com",
            issued_reason="Allow candidate-only action intents for preflight tests.",
            source_refs=["docs/product-north-star.md"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        return grant.agent_authority_grant_id

    def _bind_authority(
        self,
        action_intent_id: str,
        *,
        author_type: str = "agent",
        author_id: str = "agent:research",
        grant_id: str | None = None,
        action: str = "reduce_exposure",
        source_rule_ref: str | None = None,
    ):
        return create_action_intent_authority_binding(
            action_intent_id=action_intent_id,
            author_type=author_type,  # type: ignore[arg-type]
            author_id=author_id,
            agent_authority_grant_id=grant_id,
            requested_scope=self._authority_scope(action=action),
            source_rule_ref=source_rule_ref,
            source_refs=["context://preflight_authority_binding"],
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

    def _preflight(self, action_intent_id: str) -> dict[str, object]:
        response = self.client.get(f"/action-intents/{action_intent_id}/preflight")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _simulation_request(
        self,
        intent: dict[str, object],
        preflight: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "expected_action_intent_receipt_ref": intent["receipt_ref"],
            "expected_action_preflight_report_hash": preflight["report_hash"],
            "simulation_reason": "Describe downstream impact before any stronger artifact.",
            "scenario_mode": "descriptive_v0",
            "assumptions": {"scope": "qualitative"},
            "source_refs": ["context://simulation_request"],
        }
        payload.update(overrides)
        return payload

    def _create_simulation(
        self,
        intent: dict[str, object],
        preflight: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        response = self.client.post(
            f"/action-intents/{intent['action_intent_id']}/simulation-reports",
            json=self._simulation_request(intent, preflight, **overrides),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _trade_plan_request(
        self,
        intent: dict[str, object],
        preflight: dict[str, object],
        simulation_report: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "expected_action_intent_receipt_ref": intent["receipt_ref"],
            "expected_action_preflight_report_hash": preflight["report_hash"],
            "expected_simulation_report_receipt_ref": simulation_report["receipt_ref"],
            "plan_reason": "Shape a pre-trade plan for later authority review.",
            "plan_scope": {
                "plan_direction": "reduce",
                "target_scope": {"scope_type": "single_instrument", "symbol": "XYZ"},
                "instrument_scope": {"instrument_ref": "instrument://XYZ", "symbol": "XYZ"},
                "account_scope": {"scope_type": "portfolio_review"},
                "risk_constraints": {"risk_budget_ref": "risk-budget://concentration"},
                "notional_cap": {"currency": "USD", "max_amount": "1000"},
                "percent_cap": {"max_percent": "5"},
                "time_window": {"review_by": "2026-07-10"},
                "required_authority_level": "authority_contract_required",
            },
            "source_refs": ["context://trade_plan_candidate"],
        }
        payload.update(overrides)
        return payload

    def _create_trade_plan_candidate(
        self,
        intent: dict[str, object],
        preflight: dict[str, object],
        simulation_report: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        response = self.client.post(
            "/action-intent-simulation-reports/"
            f"{simulation_report['simulation_report_id']}/trade-plan-candidates",
            json=self._trade_plan_request(intent, preflight, simulation_report, **overrides),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

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
        self.assertEqual(body["authority_status"], "not_required")
        self.assertIsNone(body["authority_binding_id"])
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

    def test_agent_action_intent_preflight_blocks_without_authority_binding(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(created_by="agent", active_profile="review-note")

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertEqual(body["authority_status"], "missing")
        self.assertIn(
            "missing_action_intent_authority_binding",
            {finding["code"] for finding in body["findings"]},
        )

    def test_agent_action_intent_preflight_consumes_allowed_authority_binding(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(created_by="agent", active_profile="review-note")
        grant_id = self._record_grant()
        binding = self._bind_authority(intent["action_intent_id"], grant_id=grant_id).binding

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "pass")
        self.assertEqual(body["authority_status"], "allowed")
        self.assertEqual(body["authority_binding_id"], binding.binding_id)
        self.assertEqual(body["authority_binding_receipt_ref"], binding.receipt_ref)

    def test_agent_action_intent_preflight_blocks_denied_authority_binding(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(created_by="agent", active_profile="review-note")
        grant_id = self._record_grant(action="rebalance")
        binding = self._bind_authority(
            intent["action_intent_id"],
            grant_id=grant_id,
            action="rebalance",
        ).binding

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertEqual(body["authority_status"], "denied")
        self.assertEqual(body["authority_binding_id"], binding.binding_id)
        finding = next(
            item
            for item in body["findings"]
            if item["code"] == "action_intent_authority_binding_denied"
        )
        self.assertIn("action_intent_scope_mismatch", finding["recovery_hint"])
        self.assertIn(binding.receipt_ref, finding["receipt_refs"])

    def test_action_intent_preflight_blocks_stale_authority_binding_receipt(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(created_by="agent", active_profile="review-note")
        grant_id = self._record_grant()
        binding = self._bind_authority(intent["action_intent_id"], grant_id=grant_id).binding
        self._set_action_intent_fields(
            intent["action_intent_id"],
            receipt_ref="data/receipts/state-core/action-intents/receipt_newer.json",
        )

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertEqual(body["authority_status"], "stale")
        self.assertEqual(body["authority_binding_id"], binding.binding_id)
        self.assertIn(
            "stale_action_intent_authority_binding",
            {finding["code"] for finding in body["findings"]},
        )

    def test_human_action_intent_preflight_accepts_allowed_human_binding(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent()
        binding = self._bind_authority(
            intent["action_intent_id"],
            author_type="human",
            author_id="owner@example.com",
            grant_id=None,
        ).binding

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "pass")
        self.assertEqual(body["authority_status"], "allowed")
        self.assertEqual(body["authority_binding_id"], binding.binding_id)

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

    def test_preflight_bound_simulation_report_writes_receipt_and_can_be_fetched(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent()
        preflight = self._preflight(intent["action_intent_id"])

        body = self._create_simulation(intent, preflight)

        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        report = body["simulation_report"]
        self.assertEqual(report["action_intent_id"], intent["action_intent_id"])
        self.assertEqual(report["proposal_id"], self.proposal_write.proposal.proposal_id)
        self.assertEqual(report["source_action_intent_receipt_ref"], intent["receipt_ref"])
        self.assertEqual(report["source_action_preflight_report_hash"], preflight["report_hash"])
        self.assertEqual(report["source_action_preflight_status"], "pass")
        self.assertEqual(report["simulation_status"], "complete")
        self.assertEqual(report["risk_posture"], "defensive")
        self.assertEqual(report["risk_direction"], "reduce")
        self.assertEqual(report["source_action_preflight_finding_codes"], [])
        self.assertFalse(report["execution_allowed"])
        self.assertFalse(report["authority_transition"])
        self.assertNotIn("broker", report)
        self.assertNotIn("side", report)
        self.assertNotIn("quantity", report)
        self.assertNotIn("order_type", report)
        for forbidden in ("broker", "side", "quantity", "order_type"):
            self.assertNotIn(forbidden, report["numeric_impact"])

        rows = read_all(ActionIntentSimulationReport, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].receipt_ref, body["receipt_ref"])
        receipts = read_all(ReceiptIndex, engine=self.engine)
        receipt = next(
            row
            for row in receipts
            if row.kind == "state_core_action_intent_simulation_report"
        )
        self.assertEqual(receipt.path, body["receipt_ref"])
        receipt_payload = json.loads(Path(body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt_payload["kind"], "state_core_action_intent_simulation_report")
        self.assertEqual(
            receipt_payload["source_action_preflight_report_hash"],
            preflight["report_hash"],
        )
        self.assertFalse(receipt_payload["governance"]["execution_allowed"])
        self.assertFalse(receipt_payload["governance"]["authority_transition"])
        self.assertTrue(receipt_payload["governance"]["preflight_bound"])

        fetched = self.client.get(
            f"/action-intent-simulation-reports/{report['simulation_report_id']}"
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(
            fetched.json()["simulation_report"]["receipt_ref"],
            body["receipt_ref"],
        )

    def test_simulation_report_rejects_stale_preflight_hash(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent()
        preflight = self._preflight(intent["action_intent_id"])

        response = self.client.post(
            f"/action-intents/{intent['action_intent_id']}/simulation-reports",
            json=self._simulation_request(
                intent,
                preflight,
                expected_action_preflight_report_hash="sha256:stale",
            ),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(read_all(ActionIntentSimulationReport, engine=self.engine), [])

    def test_simulation_report_rejects_stale_action_intent_receipt(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent()
        preflight = self._preflight(intent["action_intent_id"])

        response = self.client.post(
            f"/action-intents/{intent['action_intent_id']}/simulation-reports",
            json=self._simulation_request(
                intent,
                preflight,
                expected_action_intent_receipt_ref="data/receipts/stale.json",
            ),
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(read_all(ActionIntentSimulationReport, engine=self.engine), [])

    def test_simulation_report_rejects_blocking_preflight(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips(restricted_actions=["reduce_exposure"])
        intent = self._create_intent()
        preflight = self._preflight(intent["action_intent_id"])
        self.assertEqual(preflight["status"], "block")

        response = self.client.post(
            f"/action-intents/{intent['action_intent_id']}/simulation-reports",
            json=self._simulation_request(intent, preflight),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"]["code"], "simulation_preflight_blocked")
        self.assertIn("ips_restricted_action_type", response.json()["detail"]["finding_codes"])

    def test_simulation_report_requires_warning_acknowledgement(self) -> None:
        intent = self._create_intent()
        preflight = self._preflight(intent["action_intent_id"])
        self.assertEqual(preflight["status"], "warn")
        warning_codes = sorted(
            {
                finding["code"]
                for finding in preflight["findings"]
                if finding["severity"] == "warning"
            }
        )
        self.assertGreaterEqual(len(warning_codes), 2)

        missing_ack = self.client.post(
            f"/action-intents/{intent['action_intent_id']}/simulation-reports",
            json=self._simulation_request(intent, preflight),
        )
        partial_ack = self.client.post(
            f"/action-intents/{intent['action_intent_id']}/simulation-reports",
            json=self._simulation_request(
                intent,
                preflight,
                explicit_preflight_acknowledgement=True,
                acknowledged_preflight_warning_codes=warning_codes[:1],
            ),
        )
        full_ack = self.client.post(
            f"/action-intents/{intent['action_intent_id']}/simulation-reports",
            json=self._simulation_request(
                intent,
                preflight,
                explicit_preflight_acknowledgement=True,
                acknowledged_preflight_warning_codes=warning_codes,
            ),
        )

        self.assertEqual(missing_ack.status_code, 422)
        self.assertEqual(partial_ack.status_code, 422)
        self.assertEqual(full_ack.status_code, 200, full_ack.text)
        report = full_ack.json()["simulation_report"]
        self.assertEqual(report["source_action_preflight_status"], "warn")
        self.assertEqual(report["simulation_status"], "incomplete")
        self.assertEqual(
            sorted(report["acknowledged_preflight_warning_codes"]),
            warning_codes,
        )

    def test_unknown_action_intent_simulation_report_targets_are_not_found(self) -> None:
        response = self.client.post(
            "/action-intents/missing/simulation-reports",
            json={
                "expected_action_intent_receipt_ref": "data/receipts/missing.json",
                "expected_action_preflight_report_hash": "sha256:missing",
                "simulation_reason": "Missing target.",
            },
        )
        fetched = self.client.get("/action-intent-simulation-reports/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(fetched.status_code, 404)

    def test_simulation_report_maps_evidence_only_action_posture(self) -> None:
        self._seed_ips()
        intent = self._create_intent(
            action_type="request_more_evidence",
            target_scope={"scope_type": "proposal"},
            intent_summary="Request more evidence before action planning.",
            rationale="The reviewed proposal needs more support.",
        )
        preflight = self._preflight(intent["action_intent_id"])
        warning_codes = [
            finding["code"]
            for finding in preflight["findings"]
            if finding["severity"] == "warning"
        ]

        body = self._create_simulation(
            intent,
            preflight,
            explicit_preflight_acknowledgement=True,
            acknowledged_preflight_warning_codes=warning_codes,
        )

        report = body["simulation_report"]
        self.assertEqual(report["risk_posture"], "evidence_only")
        self.assertEqual(report["risk_direction"], "evidence_only")
        self.assertIn("does not imply capital movement", report["qualitative_impact"]["summary"])

    def test_simulation_report_rejects_authority_markers_in_assumptions(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent()
        preflight = self._preflight(intent["action_intent_id"])

        response = self.client.post(
            f"/action-intents/{intent['action_intent_id']}/simulation-reports",
            json=self._simulation_request(
                intent,
                preflight,
                assumptions={"nested": {"execution-allowed": True}},
            ),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(ActionIntentSimulationReport, engine=self.engine), [])

    def test_trade_plan_candidate_writes_receipt_and_can_be_fetched(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]

        body = self._create_trade_plan_candidate(intent, preflight, simulation)

        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        self.assertFalse(body["submitted_to_broker"])
        candidate = body["trade_plan_candidate"]
        self.assertEqual(candidate["action_intent_id"], intent["action_intent_id"])
        self.assertEqual(candidate["simulation_report_id"], simulation["simulation_report_id"])
        self.assertEqual(candidate["proposal_id"], self.proposal_write.proposal.proposal_id)
        self.assertEqual(candidate["source_action_intent_receipt_ref"], intent["receipt_ref"])
        self.assertEqual(
            candidate["source_action_preflight_report_hash"],
            preflight["report_hash"],
        )
        self.assertEqual(
            candidate["source_simulation_report_receipt_ref"],
            simulation["receipt_ref"],
        )
        self.assertEqual(candidate["candidate_status"], "needs_authority_contract")
        self.assertEqual(candidate["plan_direction"], "reduce")
        self.assertEqual(candidate["instrument_scope"]["symbol"], "XYZ")
        self.assertEqual(candidate["notional_cap"]["max_amount"], "1000")
        self.assertEqual(candidate["percent_cap"]["max_percent"], "5")
        self.assertEqual(
            candidate["required_authority_level"],
            "authority_contract_required",
        )
        self.assertFalse(candidate["execution_allowed"])
        self.assertFalse(candidate["authority_transition"])
        self.assertFalse(candidate["submitted_to_broker"])
        self.assertNotIn("broker_order_id", candidate)
        self.assertNotIn("execution_status", candidate)
        self.assertEqual(candidate["preflight_refs"], [preflight["report_hash"]])
        self.assertNotIn(preflight["report_hash"], candidate["receipt_refs"])

        rows = read_all(TradePlanCandidate, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].receipt_ref, body["receipt_ref"])
        receipt = next(
            row
            for row in read_all(ReceiptIndex, engine=self.engine)
            if row.kind == "state_core_trade_plan_candidate"
        )
        self.assertEqual(receipt.path, body["receipt_ref"])
        receipt_payload = json.loads(Path(body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt_payload["kind"], "state_core_trade_plan_candidate")
        self.assertTrue(receipt_payload["governance"]["not_order_ticket"])
        self.assertTrue(receipt_payload["governance"]["requires_authority_contract"])
        self.assertFalse(receipt_payload["governance"]["execution_allowed"])
        self.assertFalse(receipt_payload["governance"]["authority_transition"])
        self.assertFalse(receipt_payload["governance"]["submitted_to_broker"])
        self.assertNotIn("broker_order_id", receipt_payload["governance"])
        self.assertNotIn("execution_status", receipt_payload["governance"])

        fetched = self.client.get(
            f"/trade-plan-candidates/{candidate['trade_plan_candidate_id']}"
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(
            fetched.json()["trade_plan_candidate"]["receipt_ref"],
            body["receipt_ref"],
        )

    def test_trade_plan_candidate_rejects_missing_simulation_report(self) -> None:
        response = self.client.post(
            "/action-intent-simulation-reports/missing/trade-plan-candidates",
            json={
                "expected_action_intent_receipt_ref": "data/receipts/missing_action.json",
                "expected_action_preflight_report_hash": "sha256:missing",
                "expected_simulation_report_receipt_ref": "data/receipts/missing_sim.json",
                "plan_reason": "Missing simulation report.",
                "plan_scope": {"plan_direction": "reduce"},
            },
        )
        fetched = self.client.get("/trade-plan-candidates/missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(fetched.status_code, 404)

    def test_trade_plan_candidate_rejects_stale_receipts_and_hashes(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]

        cases = (
            (
                "simulation_receipt",
                {"expected_simulation_report_receipt_ref": "data/receipts/stale_sim.json"},
            ),
            (
                "action_receipt",
                {"expected_action_intent_receipt_ref": "data/receipts/stale_action.json"},
            ),
            (
                "preflight_hash",
                {"expected_action_preflight_report_hash": "sha256:stale"},
            ),
        )
        for name, overrides in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    "/action-intent-simulation-reports/"
                    f"{simulation['simulation_report_id']}/trade-plan-candidates",
                    json=self._trade_plan_request(
                        intent,
                        preflight,
                        simulation,
                        **overrides,
                    ),
                )
                self.assertEqual(response.status_code, 409)
        self.assertEqual(read_all(TradePlanCandidate, engine=self.engine), [])

    def test_trade_plan_candidate_rejects_simulation_bound_to_stale_preflight(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        self._set_action_intent_fields(
            intent["action_intent_id"],
            target_scope={
                "scope_type": "single_instrument",
                "symbol": "ABC",
                "account_scope": "portfolio_review",
            },
        )
        current_preflight = self._preflight(intent["action_intent_id"])

        response = self.client.post(
            "/action-intent-simulation-reports/"
            f"{simulation['simulation_report_id']}/trade-plan-candidates",
            json=self._trade_plan_request(
                intent,
                current_preflight,
                simulation,
                expected_action_preflight_report_hash=current_preflight["report_hash"],
            ),
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("simulation report", response.json()["detail"])

    def test_trade_plan_candidate_rejects_blocking_current_preflight(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        self._set_action_intent_fields(
            intent["action_intent_id"],
            constraints={"execution-allowed": True},
        )
        blocked_preflight = self._preflight(intent["action_intent_id"])
        self.assertEqual(blocked_preflight["status"], "block")
        with Session(self.engine) as session:
            row = session.get(ActionIntentSimulationReport, simulation["simulation_report_id"])
            assert row is not None
            row.source_action_preflight_report_hash = blocked_preflight["report_hash"]
            row.source_action_preflight_status = "block"
            session.add(row)
            session.commit()
        simulation["source_action_preflight_report_hash"] = blocked_preflight["report_hash"]

        response = self.client.post(
            "/action-intent-simulation-reports/"
            f"{simulation['simulation_report_id']}/trade-plan-candidates",
            json=self._trade_plan_request(
                intent,
                blocked_preflight,
                simulation,
                expected_action_preflight_report_hash=blocked_preflight["report_hash"],
            ),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"]["code"],
            "trade_plan_candidate_preflight_blocked",
        )

    def test_trade_plan_candidate_requires_warning_acknowledgement(self) -> None:
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        warning_codes = sorted(
            {
                finding["code"]
                for finding in preflight["findings"]
                if finding["severity"] == "warning"
            }
        )
        simulation = self._create_simulation(
            intent,
            preflight,
            explicit_preflight_acknowledgement=True,
            acknowledged_preflight_warning_codes=warning_codes,
        )["simulation_report"]

        missing_ack = self.client.post(
            "/action-intent-simulation-reports/"
            f"{simulation['simulation_report_id']}/trade-plan-candidates",
            json=self._trade_plan_request(intent, preflight, simulation),
        )
        partial_ack = self.client.post(
            "/action-intent-simulation-reports/"
            f"{simulation['simulation_report_id']}/trade-plan-candidates",
            json=self._trade_plan_request(
                intent,
                preflight,
                simulation,
                explicit_preflight_acknowledgement=True,
                acknowledged_preflight_warning_codes=warning_codes[:1],
            ),
        )
        full_ack = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
            explicit_preflight_acknowledgement=True,
            acknowledged_preflight_warning_codes=warning_codes,
        )

        self.assertEqual(missing_ack.status_code, 422)
        self.assertEqual(partial_ack.status_code, 422)
        candidate = full_ack["trade_plan_candidate"]
        self.assertEqual(candidate["source_action_preflight_status"], "warn")
        self.assertEqual(
            sorted(candidate["acknowledged_preflight_warning_codes"]),
            warning_codes,
        )
        self.assertEqual(candidate["candidate_status"], "needs_authority_contract")

    def test_trade_plan_candidate_rejects_markers_and_exact_quantity(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        base_scope = self._trade_plan_request(intent, preflight, simulation)["plan_scope"]
        cases = (
            ("exact_quantity", {"plan_scope": {**base_scope, "quantity": 100}}),
            (
                "broker_marker",
                {"plan_scope": {**base_scope, "account_scope": {"broker": "alpaca"}}},
            ),
            (
                "execution_marker",
                {"plan_scope": {**base_scope, "notional_cap": {"execution_allowed": True}}},
            ),
            (
                "order_ready_side",
                {"plan_scope": {**base_scope, "side": "sell"}},
            ),
            (
                "submitted_to_broker",
                {"plan_scope": {**base_scope, "submitted_to_broker": True}},
            ),
            (
                "source_ref_marker",
                {"source_refs": ["broker://alpaca/order-intent"]},
            ),
        )

        for name, overrides in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    "/action-intent-simulation-reports/"
                    f"{simulation['simulation_report_id']}/trade-plan-candidates",
                    json=self._trade_plan_request(
                        intent,
                        preflight,
                        simulation,
                        **overrides,
                    ),
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(TradePlanCandidate, engine=self.engine), [])

    def test_trade_plan_candidate_rejects_unknown_closed_set_values(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        base_scope = self._trade_plan_request(intent, preflight, simulation)["plan_scope"]

        response = self.client.post(
            "/action-intent-simulation-reports/"
            f"{simulation['simulation_report_id']}/trade-plan-candidates",
            json=self._trade_plan_request(
                intent,
                preflight,
                simulation,
                plan_scope={**base_scope, "plan_direction": "sell"},
            ),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(TradePlanCandidate, engine=self.engine), [])


if __name__ == "__main__":
    unittest.main()
