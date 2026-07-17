from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session

from finharness.api.app import create_app
from finharness.ips import record_ips
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.action_intent_authority_bindings import (
    create_action_intent_authority_binding,
)
from finharness.statecore.agent_authority_grants import record_agent_authority_grant
from finharness.statecore.capital_mandates import record_capital_mandate
from finharness.statecore.models import (
    Account,
    ActionIntent,
    ActionIntentSimulationReport,
    CapitalObjectiveFit,
    PaperAccount,
    PaperExecutionReceipt,
    PaperOrderTicketCandidate,
    PaperPosition,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
    TradePlanCandidate,
    TradePlanReviewGate,
)
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core, read_all, write_records
from tests._scaffold import VALID_SCAFFOLD
from tests.asgi_test_client import AsgiTestClient
from tests.authority_test_helpers import authority_admin_context


class ActionIntentCandidateApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
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
            operator_context=authority_admin_context("owner@example.com"),
            capital_mandate_id=mandate_id,
            profile_snapshot={"profile": "balanced"},
            investment_objectives={"primary": "risk_control"},
            risk_profile={"max_drawdown_pct": 0.10},
            allowed_asset_classes=["cash", "equity"],
            restricted_asset_classes=["crypto_leverage"],
            allowed_action_types=["reduce_exposure", "rebalance", "raise_cash"],
            restricted_action_types=["open_margin"],
            autonomy_level="L1_candidate_only",
            typed_limits={
                "max_notional": {"amount": "1000", "currency": "USD"},
            },
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
            operator_context=authority_admin_context("owner@example.com"),
            agent_authority_grant_id=grant_id,
            capital_mandate_id=self._record_mandate(),
            agent_id=agent_id,
            agent_profile_name="review-note",
            grant_scope=self._authority_scope(action=action),
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

    def _increase_plan_scope(self) -> dict[str, object]:
        return {
            "plan_direction": "increase",
            "target_scope": {"scope_type": "single_instrument", "symbol": "XYZ"},
            "instrument_scope": {"instrument_ref": "instrument://XYZ", "symbol": "XYZ"},
            "account_scope": {"scope_type": "portfolio_review"},
            "risk_constraints": {"risk_budget_ref": "risk-budget://concentration"},
            "notional_cap": {"currency": "USD", "max_amount": "1000"},
            "percent_cap": {"max_percent": "5"},
            "time_window": {"review_by": "2026-07-10"},
            "required_authority_level": "authority_contract_required",
        }

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

    def _capital_objective_fit_request(
        self,
        intent: dict[str, object],
        preflight: dict[str, object],
        simulation_report: dict[str, object],
        trade_plan_candidate: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "expected_trade_plan_candidate_receipt_ref": trade_plan_candidate[
                "receipt_ref"
            ],
            "expected_action_intent_receipt_ref": intent["receipt_ref"],
            "expected_action_preflight_report_hash": preflight["report_hash"],
            "expected_simulation_report_receipt_ref": simulation_report["receipt_ref"],
            "objective_alignment": "aligned",
            "objective_basis": {
                "capital_mandate_ref": "capital-mandate://risk-control",
                "objective": "reduce concentration risk while preserving liquidity",
            },
            "benefit_thesis": (
                "Candidate may reduce concentration risk while preserving staged review."
            ),
            "risk_budget_impact": {"direction": "risk_reduction"},
            "liquidity_impact": {"expected_effect": "neutral_to_positive"},
            "concentration_impact": {"single_name_exposure": "lower"},
            "reversibility": {"path": "staged_review_before_next_gate"},
            "opportunity_cost": {"main_cost": "possible upside foregone"},
            "alternatives_considered": [
                {
                    "path": "watchlist",
                    "reason": "defer until more evidence is available",
                }
            ],
            "major_uncertainties": ["future price path remains unknown"],
            "user_questions": ["Is reducing exposure aligned with the IPS objective?"],
            "recommended_next_safe_path": (
                "Use this objective fit as review evidence before any staging gate."
            ),
            "source_refs": ["context://capital_objective_fit"],
        }
        payload.update(overrides)
        return payload

    def _create_capital_objective_fit(
        self,
        intent: dict[str, object],
        preflight: dict[str, object],
        simulation_report: dict[str, object],
        trade_plan_candidate: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        response = self.client.post(
            f"/trade-plan-candidates/{trade_plan_candidate['trade_plan_candidate_id']}"
            "/capital-objective-fits",
            json=self._capital_objective_fit_request(
                intent,
                preflight,
                simulation_report,
                trade_plan_candidate,
                **overrides,
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _trade_plan_review_gate_request(
        self,
        intent: dict[str, object],
        preflight: dict[str, object],
        simulation_report: dict[str, object],
        trade_plan_candidate: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "expected_trade_plan_candidate_receipt_ref": trade_plan_candidate[
                "receipt_ref"
            ],
            "expected_action_intent_receipt_ref": intent["receipt_ref"],
            "expected_action_preflight_report_hash": preflight["report_hash"],
            "expected_simulation_report_receipt_ref": simulation_report["receipt_ref"],
            "review_decision": "allow_order_ticket_candidate_staging",
            "reviewer_type": "human",
            "reviewer_id": "owner@example.com",
            "review_reason": (
                "Reviewed preflight, simulation, and plan scope for candidate "
                "staging only."
            ),
            "review_context": {"review_surface": "trade_plan_review_gate_v0"},
            "review_findings": [
                {
                    "code": "candidate_scope_reviewed",
                    "severity": "info",
                    "source": "human_review",
                }
            ],
            "source_refs": ["context://trade_plan_review_gate"],
        }
        payload.update(overrides)
        return payload

    def _create_trade_plan_review_gate(
        self,
        intent: dict[str, object],
        preflight: dict[str, object],
        simulation_report: dict[str, object],
        trade_plan_candidate: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        response = self.client.post(
            f"/trade-plan-candidates/{trade_plan_candidate['trade_plan_candidate_id']}"
            "/review-gates",
            json=self._trade_plan_review_gate_request(
                intent,
                preflight,
                simulation_report,
                trade_plan_candidate,
                **overrides,
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _paper_order_ticket_request(
        self,
        intent: dict[str, object],
        preflight: dict[str, object],
        simulation_report: dict[str, object],
        trade_plan_candidate: dict[str, object],
        review_gate: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        paper_account_id = getattr(self, "_default_paper_account_id", "")
        if not paper_account_id:
            paper_account = self._create_paper_account()["paper_account"]
            paper_account_id = paper_account["paper_account_id"]
        payload: dict[str, object] = {
            "review_gate_id": review_gate["review_gate_id"],
            "expected_trade_plan_candidate_receipt_ref": trade_plan_candidate[
                "receipt_ref"
            ],
            "expected_review_gate_receipt_ref": review_gate["receipt_ref"],
            "expected_action_intent_receipt_ref": intent["receipt_ref"],
            "expected_action_preflight_report_hash": preflight["report_hash"],
            "expected_simulation_report_receipt_ref": simulation_report["receipt_ref"],
            "ticket": {
                "environment": "paper",
                "paper_account_ref": paper_account_id,
                "instrument_ref": "instrument://XYZ",
                "symbol": "XYZ",
                "side": "sell",
                "order_type": "limit",
                "time_in_force": "day",
                "quantity": "2",
                "limit_price": "101.25",
                "currency": "USD",
                "ticket_rationale": "Paper-validate the reviewed reduction plan.",
            },
            "source_refs": ["paper://ticket-candidate/request"],
        }
        payload.update(overrides)
        return payload

    def _create_paper_order_ticket(
        self,
        intent: dict[str, object],
        preflight: dict[str, object],
        simulation_report: dict[str, object],
        trade_plan_candidate: dict[str, object],
        review_gate: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        response = self.client.post(
            f"/trade-plan-candidates/{trade_plan_candidate['trade_plan_candidate_id']}"
            "/paper-order-ticket-candidates",
            json=self._paper_order_ticket_request(
                intent,
                preflight,
                simulation_report,
                trade_plan_candidate,
                review_gate,
                **overrides,
            ),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _paper_execution_request(
        self,
        paper_ticket: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "expected_paper_order_ticket_receipt_ref": paper_ticket["receipt_ref"],
            "execution_status": "simulated_filled",
            "fill_price": "101.10",
            "simulator_ref": "paper-simulator://local/v0",
            "fees": "0.25",
            "execution_notes": ["local deterministic paper fill"],
            "source_refs": ["paper://execution/request"],
        }
        payload.update(overrides)
        return payload

    def _create_paper_execution(
        self,
        paper_ticket: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        response = self.client.post(
            f"/paper-order-ticket-candidates/{paper_ticket['paper_order_ticket_id']}"
            "/simulated-executions",
            json=self._paper_execution_request(paper_ticket, **overrides),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _create_paper_account(self, **overrides: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "display_name": "Local paper account",
            "starting_cash": "10000",
            "currency": "USD",
            "source_refs": ["paper://account/request"],
        }
        payload.update(overrides)
        response = self.client.post("/paper-accounts", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self._default_paper_account_id = body["paper_account"]["paper_account_id"]
        return body

    def _paper_account_application_request(
        self,
        paper_account: dict[str, object],
        paper_execution: dict[str, object],
        **overrides: object,
    ) -> dict[str, object]:
        execution = paper_execution["paper_execution"]
        payload: dict[str, object] = {
            "paper_execution_id": execution["paper_execution_id"],
            "expected_paper_account_receipt_ref": paper_account["receipt_ref"],
            "expected_paper_execution_receipt_ref": paper_execution["receipt_ref"],
            "source_refs": ["paper://account/application/request"],
        }
        payload.update(overrides)
        return payload

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

    def test_human_action_intent_preflight_blocks_denied_human_binding(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent()
        binding = self._bind_authority(
            intent["action_intent_id"],
            author_type="human",
            author_id="owner@example.com",
            grant_id=None,
            action="rebalance",
        ).binding

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertEqual(body["authority_status"], "denied")
        self.assertEqual(body["authority_binding_id"], binding.binding_id)
        self.assertIn(
            "action_intent_authority_binding_denied",
            {finding["code"] for finding in body["findings"]},
        )

    def test_action_intent_preflight_prioritizes_author_mismatch_status(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(created_by="agent", active_profile="review-note")
        binding = self._bind_authority(
            intent["action_intent_id"],
            author_type="human",
            author_id="owner@example.com",
            grant_id=None,
        ).binding

        response = self.client.get(f"/action-intents/{intent['action_intent_id']}/preflight")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "block")
        self.assertEqual(body["authority_status"], "mismatched")
        self.assertEqual(body["authority_binding_id"], binding.binding_id)
        finding_codes = {finding["code"] for finding in body["findings"]}
        self.assertIn("action_intent_authority_binding_author_mismatch", finding_codes)
        self.assertIn("action_intent_authority_binding_denied", finding_codes)

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
        intent = self._create_intent(
            action_type="increase_exposure",
            intent_summary="Consider increasing single-name exposure.",
            rationale="Reviewed proposal indicates a paper buy plan should be validated.",
            expected_next_step="simulation",
        )
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

    def test_capital_objective_fit_writes_receipt_and_can_be_fetched(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(
            action_type="increase_exposure",
            intent_summary="Consider increasing single-name exposure.",
            rationale="Reviewed proposal indicates a paper buy plan should be validated.",
            expected_next_step="simulation",
        )
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
            plan_scope=self._increase_plan_scope(),
        )["trade_plan_candidate"]

        body = self._create_capital_objective_fit(intent, preflight, simulation, candidate)

        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        self.assertFalse(body["submitted_to_broker"])
        self.assertFalse(body["creates_order_ticket"])
        self.assertFalse(body["suitability_certified"])
        self.assertFalse(body["approval_granted"])
        objective_fit = body["objective_fit"]
        self.assertEqual(
            objective_fit["trade_plan_candidate_id"],
            candidate["trade_plan_candidate_id"],
        )
        self.assertEqual(objective_fit["action_intent_id"], intent["action_intent_id"])
        self.assertEqual(
            objective_fit["simulation_report_id"],
            simulation["simulation_report_id"],
        )
        self.assertEqual(
            objective_fit["source_trade_plan_candidate_receipt_ref"],
            candidate["receipt_ref"],
        )
        self.assertEqual(objective_fit["source_action_intent_receipt_ref"], intent["receipt_ref"])
        self.assertEqual(
            objective_fit["source_action_preflight_report_hash"],
            preflight["report_hash"],
        )
        self.assertEqual(
            objective_fit["source_simulation_report_receipt_ref"],
            simulation["receipt_ref"],
        )
        self.assertEqual(objective_fit["objective_alignment"], "aligned")
        self.assertEqual(objective_fit["risk_budget_impact"]["direction"], "risk_reduction")
        self.assertEqual(objective_fit["preflight_refs"], [preflight["report_hash"]])
        self.assertNotIn(preflight["report_hash"], objective_fit["receipt_refs"])

        rows = read_all(CapitalObjectiveFit, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].receipt_ref, body["receipt_ref"])
        receipt = next(
            row
            for row in read_all(ReceiptIndex, engine=self.engine)
            if row.kind == "state_core_capital_objective_fit"
        )
        self.assertEqual(receipt.path, body["receipt_ref"])
        receipt_payload = json.loads(Path(body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt_payload["kind"], "state_core_capital_objective_fit")
        self.assertTrue(receipt_payload["governance"]["objective_fit_only"])
        self.assertTrue(receipt_payload["governance"]["not_investment_advice"])
        self.assertTrue(receipt_payload["governance"]["not_trade_plan_approval"])
        self.assertTrue(receipt_payload["governance"]["not_order_ticket"])
        self.assertFalse(receipt_payload["governance"]["suitability_certified"])
        self.assertFalse(receipt_payload["governance"]["approval_granted"])
        self.assertFalse(receipt_payload["governance"]["execution_allowed"])

        fetched = self.client.get(
            f"/capital-objective-fits/{objective_fit['capital_objective_fit_id']}"
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["objective_fit"]["receipt_ref"], body["receipt_ref"])
        self.assertFalse(fetched.json()["approval_granted"])

    def test_capital_objective_fit_rejects_stale_evidence(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(
            action_type="increase_exposure",
            intent_summary="Consider increasing single-name exposure.",
            rationale="Reviewed proposal indicates a paper buy plan should be validated.",
            expected_next_step="simulation",
        )
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
            plan_scope=self._increase_plan_scope(),
        )["trade_plan_candidate"]
        cases = (
            (
                "candidate_receipt",
                {
                    "expected_trade_plan_candidate_receipt_ref": (
                        "data/receipts/stale_candidate.json"
                    )
                },
            ),
            (
                "action_receipt",
                {"expected_action_intent_receipt_ref": "data/receipts/stale_action.json"},
            ),
            (
                "preflight_hash",
                {"expected_action_preflight_report_hash": "sha256:stale"},
            ),
            (
                "simulation_receipt",
                {
                    "expected_simulation_report_receipt_ref": (
                        "data/receipts/stale_simulation.json"
                    )
                },
            ),
        )

        for name, overrides in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    f"/trade-plan-candidates/{candidate['trade_plan_candidate_id']}"
                    "/capital-objective-fits",
                    json=self._capital_objective_fit_request(
                        intent,
                        preflight,
                        simulation,
                        candidate,
                        **overrides,
                    ),
                )
                self.assertEqual(response.status_code, 409)
        self.assertEqual(read_all(CapitalObjectiveFit, engine=self.engine), [])

    def test_capital_objective_fit_rejects_advice_and_order_markers(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
            plan_scope=self._increase_plan_scope(),
        )["trade_plan_candidate"]
        cases = (
            ("advice", {"objective_basis": {"investment_advice": "buy"}}),
            ("approval", {"risk_budget_impact": {"approval_granted": True}}),
            ("order_alias", {"alternatives_considered": [{"shares": 10}]}),
            (
                "benefit_text_advice",
                {
                    "benefit_thesis": (
                        "This is investment advice to buy 100 shares."
                    )
                },
            ),
            (
                "next_path_broker_order",
                {"recommended_next_safe_path": "Submit broker order now."},
            ),
            (
                "source_ref_broker",
                {"source_refs": ["broker://unsafe-order-ticket"]},
            ),
            (
                "unclear_without_questions",
                {
                    "objective_alignment": "unclear",
                    "major_uncertainties": [],
                    "user_questions": [],
                },
            ),
        )
        for name, overrides in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    f"/trade-plan-candidates/{candidate['trade_plan_candidate_id']}"
                    "/capital-objective-fits",
                    json=self._capital_objective_fit_request(
                        intent,
                        preflight,
                        simulation,
                        candidate,
                        **overrides,
                    ),
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(CapitalObjectiveFit, engine=self.engine), [])

    def test_trade_plan_review_gate_writes_allow_receipt_and_can_be_fetched(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(
            action_type="increase_exposure",
            intent_summary="Consider increasing single-name exposure.",
            rationale="Reviewed proposal indicates a paper buy plan should be validated.",
            expected_next_step="simulation",
        )
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
            plan_scope=self._increase_plan_scope(),
        )["trade_plan_candidate"]

        body = self._create_trade_plan_review_gate(intent, preflight, simulation, candidate)

        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        self.assertFalse(body["submitted_to_broker"])
        self.assertFalse(body["creates_order_ticket"])
        gate = body["review_gate"]
        self.assertEqual(gate["trade_plan_candidate_id"], candidate["trade_plan_candidate_id"])
        self.assertEqual(gate["action_intent_id"], intent["action_intent_id"])
        self.assertEqual(gate["simulation_report_id"], simulation["simulation_report_id"])
        self.assertEqual(
            gate["source_trade_plan_candidate_receipt_ref"],
            candidate["receipt_ref"],
        )
        self.assertEqual(gate["source_action_intent_receipt_ref"], intent["receipt_ref"])
        self.assertEqual(
            gate["source_action_preflight_report_hash"],
            preflight["report_hash"],
        )
        self.assertEqual(
            gate["source_simulation_report_receipt_ref"],
            simulation["receipt_ref"],
        )
        self.assertEqual(
            gate["review_decision"],
            "allow_order_ticket_candidate_staging",
        )
        self.assertEqual(gate["reviewer_type"], "human")
        self.assertTrue(gate["may_enter_order_ticket_candidate_staging"])
        self.assertFalse(gate["execution_allowed"])
        self.assertFalse(gate["authority_transition"])
        self.assertFalse(gate["submitted_to_broker"])
        self.assertFalse(gate["creates_order_ticket"])
        self.assertEqual(gate["preflight_refs"], [preflight["report_hash"]])
        self.assertNotIn(preflight["report_hash"], gate["receipt_refs"])

        rows = read_all(TradePlanReviewGate, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].receipt_ref, body["receipt_ref"])
        receipt = next(
            row
            for row in read_all(ReceiptIndex, engine=self.engine)
            if row.kind == "state_core_trade_plan_review_gate"
        )
        self.assertEqual(receipt.path, body["receipt_ref"])
        receipt_payload = json.loads(Path(body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt_payload["kind"], "state_core_trade_plan_review_gate")
        self.assertTrue(receipt_payload["governance"]["review_gate_only"])
        self.assertTrue(receipt_payload["governance"]["not_order_ticket"])
        self.assertTrue(receipt_payload["governance"]["not_authority_contract"])
        self.assertTrue(receipt_payload["governance"]["may_enter_order_ticket_candidate_staging"])
        self.assertFalse(receipt_payload["governance"]["creates_order_ticket"])
        self.assertFalse(receipt_payload["governance"]["submitted_to_broker"])
        self.assertFalse(receipt_payload["governance"]["execution_allowed"])
        self.assertFalse(receipt_payload["governance"]["authority_transition"])

        fetched = self.client.get(f"/trade-plan-review-gates/{gate['review_gate_id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["review_gate"]["receipt_ref"], body["receipt_ref"])
        self.assertFalse(fetched.json()["creates_order_ticket"])

    def test_paper_order_ticket_candidate_writes_order_shaped_paper_receipt(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
        )["trade_plan_candidate"]
        gate = self._create_trade_plan_review_gate(
            intent,
            preflight,
            simulation,
            candidate,
        )["review_gate"]

        body = self._create_paper_order_ticket(
            intent,
            preflight,
            simulation,
            candidate,
            gate,
        )

        self.assertEqual(body["environment"], "paper")
        self.assertFalse(body["live_execution_allowed"])
        self.assertFalse(body["real_cash_at_risk"])
        self.assertFalse(body["submitted_to_broker"])
        ticket = body["paper_order_ticket"]
        self.assertEqual(ticket["environment"], "paper")
        self.assertEqual(ticket["trade_plan_candidate_id"], candidate["trade_plan_candidate_id"])
        self.assertEqual(ticket["review_gate_id"], gate["review_gate_id"])
        self.assertEqual(ticket["symbol"], "XYZ")
        self.assertEqual(ticket["side"], "sell")
        self.assertEqual(ticket["order_type"], "limit")
        self.assertEqual(ticket["quantity"], "2")
        self.assertEqual(ticket["limit_price"], "101.25")
        self.assertFalse(ticket["live_execution_allowed"])
        self.assertFalse(ticket["real_cash_at_risk"])
        self.assertFalse(ticket["submitted_to_broker"])

        rows = read_all(PaperOrderTicketCandidate, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].receipt_ref, body["receipt_ref"])
        receipt = next(
            row
            for row in read_all(ReceiptIndex, engine=self.engine)
            if row.kind == "state_core_paper_order_ticket_candidate"
        )
        self.assertEqual(receipt.path, body["receipt_ref"])
        receipt_payload = json.loads(Path(body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(
            receipt_payload["kind"],
            "state_core_paper_order_ticket_candidate",
        )
        self.assertTrue(receipt_payload["governance"]["order_fields_allowed_in_this_artifact"])
        self.assertEqual(receipt_payload["governance"]["environment"], "paper")
        self.assertFalse(receipt_payload["governance"]["live_execution_allowed"])
        self.assertFalse(receipt_payload["governance"]["real_cash_at_risk"])
        self.assertFalse(receipt_payload["governance"]["submitted_to_broker"])

        fetched = self.client.get(
            f"/paper-order-ticket-candidates/{ticket['paper_order_ticket_id']}"
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(
            fetched.json()["paper_order_ticket"]["receipt_ref"],
            body["receipt_ref"],
        )
        listed = self.client.get("/paper-order-ticket-candidates")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            listed.json()["paper_order_tickets"][0]["paper_order_ticket_id"],
            ticket["paper_order_ticket_id"],
        )

    def test_paper_order_ticket_candidate_requires_allowed_review_gate(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
        )["trade_plan_candidate"]
        denied_gate = self._create_trade_plan_review_gate(
            intent,
            preflight,
            simulation,
            candidate,
            review_decision="deny_order_ticket_candidate_staging",
            deny_reasons=["scope_requires_more_evidence"],
            review_reason="Candidate scope needs more evidence before staging.",
        )["review_gate"]

        response = self.client.post(
            f"/trade-plan-candidates/{candidate['trade_plan_candidate_id']}"
            "/paper-order-ticket-candidates",
            json=self._paper_order_ticket_request(
                intent,
                preflight,
                simulation,
                candidate,
                denied_gate,
            ),
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("requires an allowed", response.text)
        self.assertEqual(read_all(PaperOrderTicketCandidate, engine=self.engine), [])

    def test_paper_order_ticket_candidate_rejects_live_or_submit_markers(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
        )["trade_plan_candidate"]
        gate = self._create_trade_plan_review_gate(
            intent,
            preflight,
            simulation,
            candidate,
        )["review_gate"]
        base_ticket = self._paper_order_ticket_request(
            intent,
            preflight,
            simulation,
            candidate,
            gate,
        )["ticket"]
        cases = (
            ("live_environment", {"ticket": {**base_ticket, "environment": "live"}}),
            (
                "submitted_to_broker",
                {"ticket": {**base_ticket, "submitted_to_broker": True}},
            ),
            (
                "real_cash_at_risk",
                {"ticket": {**base_ticket, "real_cash_at_risk": True}},
            ),
            (
                "live_source_ref",
                {"source_refs": ["live://broker/order"]},
            ),
            ("zero_limit_price", {"ticket": {**base_ticket, "limit_price": "0"}}),
            (
                "negative_stop_price",
                {
                    "ticket": {
                        **base_ticket,
                        "order_type": "stop_limit",
                        "stop_price": "-1",
                    }
                },
            ),
            (
                "negative_notional_estimate",
                {"ticket": {**base_ticket, "notional_estimate": "-1"}},
            ),
        )
        for name, overrides in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    f"/trade-plan-candidates/{candidate['trade_plan_candidate_id']}"
                    "/paper-order-ticket-candidates",
                    json=self._paper_order_ticket_request(
                        intent,
                        preflight,
                        simulation,
                        candidate,
                        gate,
                        **overrides,
                    ),
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(PaperOrderTicketCandidate, engine=self.engine), [])

    def test_paper_order_ticket_candidate_validates_paper_account(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
        )["trade_plan_candidate"]
        gate = self._create_trade_plan_review_gate(
            intent,
            preflight,
            simulation,
            candidate,
        )["review_gate"]
        base_ticket = self._paper_order_ticket_request(
            intent,
            preflight,
            simulation,
            candidate,
            gate,
        )["ticket"]

        missing_account = self.client.post(
            f"/trade-plan-candidates/{candidate['trade_plan_candidate_id']}"
            "/paper-order-ticket-candidates",
            json=self._paper_order_ticket_request(
                intent,
                preflight,
                simulation,
                candidate,
                gate,
                ticket={**base_ticket, "paper_account_ref": "paper_account_missing"},
            ),
        )
        self.assertEqual(missing_account.status_code, 404)

        currency_mismatch = self.client.post(
            f"/trade-plan-candidates/{candidate['trade_plan_candidate_id']}"
            "/paper-order-ticket-candidates",
            json=self._paper_order_ticket_request(
                intent,
                preflight,
                simulation,
                candidate,
                gate,
                ticket={**base_ticket, "currency": "EUR"},
            ),
        )
        self.assertEqual(currency_mismatch.status_code, 422)
        self.assertIn("currency", currency_mismatch.text)
        self.assertEqual(read_all(PaperOrderTicketCandidate, engine=self.engine), [])

    def test_paper_execution_receipt_records_simulated_fill(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
        )["trade_plan_candidate"]
        gate = self._create_trade_plan_review_gate(
            intent,
            preflight,
            simulation,
            candidate,
        )["review_gate"]
        paper_ticket = self._create_paper_order_ticket(
            intent,
            preflight,
            simulation,
            candidate,
            gate,
        )["paper_order_ticket"]

        body = self._create_paper_execution(paper_ticket)

        self.assertEqual(body["environment"], "paper")
        self.assertFalse(body["live_execution_allowed"])
        self.assertFalse(body["real_cash_at_risk"])
        self.assertFalse(body["submitted_to_broker"])
        execution = body["paper_execution"]
        self.assertEqual(execution["paper_order_ticket_id"], paper_ticket["paper_order_ticket_id"])
        self.assertEqual(execution["execution_status"], "simulated_filled")
        self.assertEqual(execution["symbol"], "XYZ")
        self.assertEqual(execution["side"], "sell")
        self.assertEqual(execution["quantity"], "2")
        self.assertEqual(execution["fill_price"], "101.10")
        self.assertEqual(execution["gross_notional"], "202.20")
        self.assertEqual(execution["fees"], "0.25")
        self.assertFalse(execution["live_execution_allowed"])
        self.assertFalse(execution["real_cash_at_risk"])
        self.assertFalse(execution["submitted_to_broker"])

        rows = read_all(PaperExecutionReceipt, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].receipt_ref, body["receipt_ref"])
        receipt = next(
            row
            for row in read_all(ReceiptIndex, engine=self.engine)
            if row.kind == "state_core_paper_execution_receipt"
        )
        self.assertEqual(receipt.path, body["receipt_ref"])
        receipt_payload = json.loads(Path(body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt_payload["kind"], "state_core_paper_execution_receipt")
        self.assertTrue(receipt_payload["governance"]["simulator_result"])
        self.assertFalse(receipt_payload["governance"]["live_execution_allowed"])
        self.assertFalse(receipt_payload["governance"]["real_cash_at_risk"])
        self.assertFalse(receipt_payload["governance"]["submitted_to_broker"])

        fetched = self.client.get(
            f"/paper-execution-receipts/{execution['paper_execution_id']}"
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(
            fetched.json()["paper_execution"]["receipt_ref"],
            body["receipt_ref"],
        )
        listed = self.client.get("/paper-execution-receipts")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            listed.json()["paper_executions"][0]["paper_execution_id"],
            execution["paper_execution_id"],
        )

    def test_paper_execution_receipt_rejects_stale_or_live_markers(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
        )["trade_plan_candidate"]
        gate = self._create_trade_plan_review_gate(
            intent,
            preflight,
            simulation,
            candidate,
        )["review_gate"]
        paper_ticket = self._create_paper_order_ticket(
            intent,
            preflight,
            simulation,
            candidate,
            gate,
        )["paper_order_ticket"]
        cases = (
            (
                "stale_ticket_receipt",
                {"expected_paper_order_ticket_receipt_ref": "data/receipts/stale.json"},
                409,
            ),
            ("live_simulator_ref", {"simulator_ref": "live://broker/simulator"}, 422),
            ("live_source_ref", {"source_refs": ["live://broker/fill"]}, 422),
            ("negative_fee", {"fees": "-1"}, 422),
        )
        for name, overrides, status_code in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    f"/paper-order-ticket-candidates/{paper_ticket['paper_order_ticket_id']}"
                    "/simulated-executions",
                    json=self._paper_execution_request(paper_ticket, **overrides),
                )
                self.assertEqual(response.status_code, status_code)
        self.assertEqual(read_all(PaperExecutionReceipt, engine=self.engine), [])

    def test_paper_execution_receipt_records_rejection_without_fill(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
        )["trade_plan_candidate"]
        gate = self._create_trade_plan_review_gate(
            intent,
            preflight,
            simulation,
            candidate,
        )["review_gate"]
        paper_ticket = self._create_paper_order_ticket(
            intent,
            preflight,
            simulation,
            candidate,
            gate,
        )["paper_order_ticket"]

        body = self._create_paper_execution(
            paper_ticket,
            execution_status="simulated_rejected",
            fill_price=None,
            fees="0",
            rejection_reason="paper simulator rejected the ticket for insufficient position.",
        )

        execution = body["paper_execution"]
        self.assertEqual(execution["execution_status"], "simulated_rejected")
        self.assertEqual(execution["fill_price"], "0")
        self.assertEqual(execution["gross_notional"], "0")
        self.assertEqual(execution["fees"], "0")
        self.assertEqual(
            execution["rejection_reason"],
            "paper simulator rejected the ticket for insufficient position.",
        )

        response = self.client.post(
            f"/paper-order-ticket-candidates/{paper_ticket['paper_order_ticket_id']}"
            "/simulated-executions",
            json=self._paper_execution_request(
                paper_ticket,
                execution_status="simulated_rejected",
                fill_price="1",
                fees="0",
                rejection_reason="invalid rejected fill",
            ),
        )
        self.assertEqual(response.status_code, 422)

    def test_paper_account_writes_paper_only_receipt(self) -> None:
        body = self._create_paper_account()

        self.assertEqual(body["environment"], "paper")
        self.assertFalse(body["live_execution_allowed"])
        self.assertFalse(body["real_cash_at_risk"])
        self.assertFalse(body["submitted_to_broker"])
        account = body["paper_account"]
        self.assertEqual(account["environment"], "paper")
        self.assertEqual(account["display_name"], "Local paper account")
        self.assertEqual(account["cash_balance"], "10000")
        self.assertEqual(account["realized_pnl"], "0")
        self.assertFalse(account["live_execution_allowed"])
        self.assertFalse(account["real_cash_at_risk"])
        self.assertFalse(account["submitted_to_broker"])

        rows = read_all(PaperAccount, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].receipt_ref, body["receipt_ref"])
        receipt = next(
            row
            for row in read_all(ReceiptIndex, engine=self.engine)
            if row.kind == "state_core_paper_account"
        )
        self.assertEqual(receipt.path, body["receipt_ref"])
        receipt_payload = json.loads(Path(body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt_payload["kind"], "state_core_paper_account")
        self.assertEqual(receipt_payload["governance"]["environment"], "paper")
        self.assertFalse(receipt_payload["governance"]["live_execution_allowed"])
        self.assertFalse(receipt_payload["governance"]["real_cash_at_risk"])
        self.assertFalse(receipt_payload["governance"]["submitted_to_broker"])

        fetched = self.client.get(f"/paper-accounts/{account['paper_account_id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["paper_account"]["receipt_ref"], body["receipt_ref"])
        listed = self.client.get("/paper-accounts")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            listed.json()["paper_accounts"][0]["paper_account_id"],
            account["paper_account_id"],
        )

    def test_paper_account_application_updates_cash_and_position(self) -> None:
        paper_account_body = self._create_paper_account()
        paper_account = paper_account_body["paper_account"]
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(
            action_type="increase_exposure",
            intent_summary="Consider increasing single-name exposure.",
            rationale="Reviewed proposal indicates a paper buy plan should be validated.",
            expected_next_step="simulation",
        )
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
            plan_scope=self._increase_plan_scope(),
        )["trade_plan_candidate"]
        gate = self._create_trade_plan_review_gate(
            intent,
            preflight,
            simulation,
            candidate,
        )["review_gate"]
        base_ticket = self._paper_order_ticket_request(
            intent,
            preflight,
            simulation,
            candidate,
            gate,
        )["ticket"]
        paper_ticket = self._create_paper_order_ticket(
            intent,
            preflight,
            simulation,
            candidate,
            gate,
            ticket={
                **base_ticket,
                "paper_account_ref": paper_account["paper_account_id"],
                "side": "buy",
                "quantity": "2",
                "limit_price": "101.25",
                "ticket_rationale": "Paper-validate the reviewed buy plan.",
            },
        )["paper_order_ticket"]
        paper_execution_body = self._create_paper_execution(paper_ticket)

        response = self.client.post(
            f"/paper-accounts/{paper_account['paper_account_id']}/execution-applications",
            json=self._paper_account_application_request(
                paper_account_body,
                paper_execution_body,
            ),
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["environment"], "paper")
        self.assertFalse(body["live_execution_allowed"])
        self.assertFalse(body["real_cash_at_risk"])
        self.assertFalse(body["submitted_to_broker"])
        account = body["paper_account"]
        position = body["paper_position"]
        self.assertEqual(account["cash_balance"], "9797.55")
        self.assertEqual(account["realized_pnl"], "0")
        self.assertEqual(
            account["applied_paper_execution_ids"],
            [paper_execution_body["paper_execution"]["paper_execution_id"]],
        )
        self.assertEqual(position["symbol"], "XYZ")
        self.assertEqual(position["quantity"], "2")
        self.assertEqual(position["average_cost"], "101.225")
        self.assertEqual(position["last_price"], "101.10")
        self.assertEqual(position["market_value"], "202.20")

        account_rows = read_all(PaperAccount, engine=self.engine)
        position_rows = read_all(PaperPosition, engine=self.engine)
        self.assertEqual(len(account_rows), 1)
        self.assertEqual(len(position_rows), 1)
        self.assertEqual(account_rows[0].receipt_ref, body["receipt_ref"])
        self.assertEqual(position_rows[0].receipt_ref, body["receipt_ref"])
        receipt = next(
            row
            for row in read_all(ReceiptIndex, engine=self.engine)
            if row.kind == "state_core_paper_account_execution_application"
        )
        self.assertEqual(receipt.path, body["receipt_ref"])
        receipt_payload = json.loads(Path(body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(
            receipt_payload["kind"],
            "state_core_paper_account_execution_application",
        )
        self.assertEqual(receipt_payload["before"]["account"]["cash_balance"], "10000")
        self.assertEqual(receipt_payload["after"]["account"]["cash_balance"], "9797.55")
        self.assertFalse(receipt_payload["governance"]["real_cash_at_risk"])
        positions = self.client.get(
            f"/paper-accounts/{paper_account['paper_account_id']}/positions"
        )
        self.assertEqual(positions.status_code, 200)
        self.assertEqual(
            positions.json()["paper_positions"][0]["paper_position_id"],
            position["paper_position_id"],
        )

    def test_paper_account_application_rejects_stale_replay_and_live_markers(self) -> None:
        paper_account_body = self._create_paper_account()
        paper_account = paper_account_body["paper_account"]
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(
            action_type="increase_exposure",
            intent_summary="Consider increasing single-name exposure.",
            rationale="Reviewed proposal indicates a paper buy plan should be validated.",
            expected_next_step="simulation",
        )
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
            plan_scope=self._increase_plan_scope(),
        )["trade_plan_candidate"]
        gate = self._create_trade_plan_review_gate(
            intent,
            preflight,
            simulation,
            candidate,
        )["review_gate"]
        base_ticket = self._paper_order_ticket_request(
            intent,
            preflight,
            simulation,
            candidate,
            gate,
        )["ticket"]
        paper_ticket = self._create_paper_order_ticket(
            intent,
            preflight,
            simulation,
            candidate,
            gate,
            ticket={
                **base_ticket,
                "paper_account_ref": paper_account["paper_account_id"],
                "side": "buy",
            },
        )["paper_order_ticket"]
        paper_execution_body = self._create_paper_execution(paper_ticket)

        stale_response = self.client.post(
            f"/paper-accounts/{paper_account['paper_account_id']}/execution-applications",
            json=self._paper_account_application_request(
                paper_account_body,
                paper_execution_body,
                expected_paper_account_receipt_ref="data/receipts/stale.json",
            ),
        )
        self.assertEqual(stale_response.status_code, 409)
        live_response = self.client.post(
            f"/paper-accounts/{paper_account['paper_account_id']}/execution-applications",
            json=self._paper_account_application_request(
                paper_account_body,
                paper_execution_body,
                source_refs=["live://broker/account-apply"],
            ),
        )
        self.assertEqual(live_response.status_code, 422)

        applied_response = self.client.post(
            f"/paper-accounts/{paper_account['paper_account_id']}/execution-applications",
            json=self._paper_account_application_request(
                paper_account_body,
                paper_execution_body,
            ),
        )
        self.assertEqual(applied_response.status_code, 200, applied_response.text)
        replay_response = self.client.post(
            f"/paper-accounts/{paper_account['paper_account_id']}/execution-applications",
            json=self._paper_account_application_request(
                {
                    **paper_account_body,
                    "receipt_ref": applied_response.json()["receipt_ref"],
                },
                paper_execution_body,
            ),
        )
        self.assertEqual(replay_response.status_code, 409)

    def test_trade_plan_review_gate_persists_denial_evidence(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
        )["trade_plan_candidate"]

        body = self._create_trade_plan_review_gate(
            intent,
            preflight,
            simulation,
            candidate,
            review_decision="deny_order_ticket_candidate_staging",
            deny_reasons=["scope_requires_more_evidence"],
            review_reason="Candidate scope needs more evidence before staging.",
        )

        gate = body["review_gate"]
        self.assertEqual(gate["review_decision"], "deny_order_ticket_candidate_staging")
        self.assertFalse(gate["may_enter_order_ticket_candidate_staging"])
        self.assertEqual(gate["deny_reasons"], ["scope_requires_more_evidence"])
        self.assertEqual(len(read_all(TradePlanReviewGate, engine=self.engine)), 1)

    def test_trade_plan_review_gate_rejects_stale_evidence(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
        )["trade_plan_candidate"]
        cases = (
            (
                "candidate_receipt",
                {
                    "expected_trade_plan_candidate_receipt_ref": (
                        "data/receipts/stale_candidate.json"
                    )
                },
            ),
            (
                "action_receipt",
                {"expected_action_intent_receipt_ref": "data/receipts/stale_action.json"},
            ),
            (
                "preflight_hash",
                {"expected_action_preflight_report_hash": "sha256:stale"},
            ),
            (
                "simulation_receipt",
                {
                    "expected_simulation_report_receipt_ref": (
                        "data/receipts/stale_simulation.json"
                    )
                },
            ),
        )

        for name, overrides in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    f"/trade-plan-candidates/{candidate['trade_plan_candidate_id']}"
                    "/review-gates",
                    json=self._trade_plan_review_gate_request(
                        intent,
                        preflight,
                        simulation,
                        candidate,
                        **overrides,
                    ),
                )
                self.assertEqual(response.status_code, 409)
        self.assertEqual(read_all(TradePlanReviewGate, engine=self.engine), [])

    def test_trade_plan_review_gate_rejects_order_ready_fields(self) -> None:
        self._seed_portfolio_snapshot()
        self._seed_ips()
        intent = self._create_intent(expected_next_step="simulation")
        preflight = self._preflight(intent["action_intent_id"])
        simulation = self._create_simulation(intent, preflight)["simulation_report"]
        candidate = self._create_trade_plan_candidate(
            intent,
            preflight,
            simulation,
        )["trade_plan_candidate"]
        cases = (
            ("quantity", {"review_context": {"quantity": 10}}),
            ("broker", {"review_context": {"broker": "alpaca"}}),
            (
                "execution_allowed",
                {"review_findings": [{"code": "x", "execution_allowed": True}]},
            ),
            (
                "blocking_finding",
                {
                    "review_findings": [
                        {"code": "needs_more_evidence", "severity": "blocking"}
                    ]
                },
            ),
            ("agent_reviewer", {"reviewer_type": "agent"}),
        )
        for name, overrides in cases:
            with self.subTest(name=name):
                response = self.client.post(
                    f"/trade-plan-candidates/{candidate['trade_plan_candidate_id']}"
                    "/review-gates",
                    json=self._trade_plan_review_gate_request(
                        intent,
                        preflight,
                        simulation,
                        candidate,
                        **overrides,
                    ),
                )
                self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(TradePlanReviewGate, engine=self.engine), [])

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
