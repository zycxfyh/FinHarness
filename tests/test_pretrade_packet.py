"""Tests for PreTradePacket read model.

Verifies the aggregate view works for:
- empty chain (no action intent exists)
- partial chain (action intent only, no downstream)
- partial chain (action intent + authority binding only)
- complete chain (all artifacts present)
- execution_allowed is always False
- next_allowed_actions is computed correctly
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.execution.pretrade_packet import (
    PreTradePacket,
    build_pretrade_packet,
)
from finharness.statecore.models import (
    ActionIntent,
    ActionIntentAuthorityBinding,
    ActionIntentSimulationReport,
    CapitalObjectiveFit,
    PaperOrderTicketCandidate,
    TradePlanCandidate,
    TradePlanReviewGate,
)
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core, write_records
from tests._scaffold import VALID_SCAFFOLD


class PreTradePacketTest(unittest.TestCase):
    """PreTradePacket builder tests with real StateCore data."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "state-core.sqlite"
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.db_path)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _proposal_id(self) -> str:
        pw = create_governed_proposal(
            kind="exposure_scan",
            claim="test proposal for pretrade_packet",
            evidence={"test": True},
            assumptions={"market": "normal"},
            limitations={"data": "synthetic"},
            non_claims=["not advice"],
            source_refs=["test://pretrade_packet"],
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=str(self.receipt_root),
        )
        return pw.proposal.proposal_id

    # ── helpers: insert models directly via write_records ─────────────────

    def _insert_action_intent(self, proposal_id: str) -> str:
        aid = f"ai_{proposal_id[-8:]}"
        write_records(
            [
                ActionIntent(
                    action_intent_id=aid,
                    proposal_id=proposal_id,
                    source_proposal_receipt_ref="test_ref",
                    created_by="agent",
                    active_profile="test",
                    action_type="reduce_exposure",
                    intent_summary="reduce risk",
                    rationale="test rationale",
                    expected_next_step="simulation",
                )
            ],
            engine=self.engine,
        )
        return aid

    def _insert_authority_binding(
        self, action_intent_id: str, proposal_id: str
    ) -> str:
        bid = f"ab_{action_intent_id[-8:]}"
        write_records(
            [
                ActionIntentAuthorityBinding(
                    binding_id=bid,
                    action_intent_id=action_intent_id,
                    proposal_id=proposal_id,
                    author_type="agent",
                    author_id="test_agent",
                    allowed=True,
                )
            ],
            engine=self.engine,
        )
        return bid

    def _insert_simulation(
        self, action_intent_id: str, proposal_id: str
    ) -> str:
        sid = f"sim_{action_intent_id[-8:]}"
        write_records(
            [
                ActionIntentSimulationReport(
                    simulation_report_id=sid,
                    action_intent_id=action_intent_id,
                    proposal_id=proposal_id,
                    source_action_intent_receipt_ref="test_ref",
                    source_action_preflight_report_hash="hash123",
                    source_action_preflight_status="pass",
                    risk_posture="moderate",
                    risk_direction="neutral",
                    scenario_mode="descriptive_v0",
                    simulation_status="complete",
                )
            ],
            engine=self.engine,
        )
        return sid

    def _insert_plan(
        self,
        action_intent_id: str,
        simulation_report_id: str,
        proposal_id: str,
    ) -> str:
        pid = f"tp_{action_intent_id[-8:]}"
        write_records(
            [
                TradePlanCandidate(
                    trade_plan_candidate_id=pid,
                    action_intent_id=action_intent_id,
                    simulation_report_id=simulation_report_id,
                    proposal_id=proposal_id,
                    source_action_intent_receipt_ref="test_ref",
                    source_action_preflight_report_hash="hash123",
                    source_simulation_report_receipt_ref="test_ref",
                    source_action_preflight_status="pass",
                    plan_direction="reduce",
                    plan_reason="test plan",
                    candidate_status="needs_authority_contract",
                )
            ],
            engine=self.engine,
        )
        return pid

    def _insert_fit(
        self,
        plan_id: str,
        action_intent_id: str,
        simulation_report_id: str,
        proposal_id: str,
    ) -> str:
        fid = f"fit_{plan_id[-8:]}"
        write_records(
            [
                CapitalObjectiveFit(
                    capital_objective_fit_id=fid,
                    trade_plan_candidate_id=plan_id,
                    action_intent_id=action_intent_id,
                    simulation_report_id=simulation_report_id,
                    proposal_id=proposal_id,
                    source_trade_plan_candidate_receipt_ref="test_ref",
                    source_action_intent_receipt_ref="test_ref",
                    source_action_preflight_report_hash="hash123",
                    source_simulation_report_receipt_ref="test_ref",
                    objective_alignment="aligned",
                    benefit_thesis="reduces risk",
                    recommended_next_safe_path="proceed",
                )
            ],
            engine=self.engine,
        )
        return fid

    def _insert_gate(
        self,
        plan_id: str,
        action_intent_id: str,
        simulation_report_id: str,
        proposal_id: str,
    ) -> str:
        gid = f"gate_{plan_id[-8:]}"
        write_records(
            [
                TradePlanReviewGate(
                    review_gate_id=gid,
                    trade_plan_candidate_id=plan_id,
                    action_intent_id=action_intent_id,
                    simulation_report_id=simulation_report_id,
                    proposal_id=proposal_id,
                    source_trade_plan_candidate_receipt_ref="test_ref",
                    source_action_intent_receipt_ref="test_ref",
                    source_action_preflight_report_hash="hash123",
                    source_simulation_report_receipt_ref="test_ref",
                    review_decision="allow_order_ticket_candidate_staging",
                    reviewer_type="human",
                    reviewer_id="test_reviewer",
                    review_reason="looks good",
                    may_enter_order_ticket_candidate_staging=True,
                )
            ],
            engine=self.engine,
        )
        return gid

    def _insert_paper_ticket(
        self,
        plan_id: str,
        gate_id: str,
        action_intent_id: str,
        simulation_report_id: str,
        proposal_id: str,
    ) -> str:
        from decimal import Decimal

        tid = f"paper_{plan_id[-8:]}"
        write_records(
            [
                PaperOrderTicketCandidate(
                    paper_order_ticket_id=tid,
                    trade_plan_candidate_id=plan_id,
                    review_gate_id=gate_id,
                    action_intent_id=action_intent_id,
                    simulation_report_id=simulation_report_id,
                    proposal_id=proposal_id,
                    source_trade_plan_candidate_receipt_ref="test_ref",
                    source_review_gate_receipt_ref="test_ref",
                    source_action_intent_receipt_ref="test_ref",
                    source_action_preflight_report_hash="hash123",
                    source_simulation_report_receipt_ref="test_ref",
                    paper_account_ref="test_acct",
                    instrument_ref="SPY",
                    symbol="SPY",
                    side="sell",
                    order_type="market",
                    quantity=Decimal("100"),
                    ticket_rationale="test paper ticket",
                )
            ],
            engine=self.engine,
        )
        return tid

    # ── tests ────────────────────────────────────────────────────────────

    def test_empty_chain(self) -> None:
        """Building a packet for a proposal with no action intent."""
        proposal_id = self._proposal_id()
        packet = build_pretrade_packet(proposal_id, self.engine)

        self.assertIsInstance(packet, PreTradePacket)
        self.assertEqual(packet.proposal_id, proposal_id)
        self.assertIsNone(packet.action_draft)
        self.assertEqual(packet.authority_findings, [])
        self.assertEqual(packet.preflight_status, "missing")
        self.assertIsNone(packet.simulation)
        self.assertIsNone(packet.plan)
        self.assertIsNone(packet.objective_fit)
        self.assertIsNone(packet.approval)
        self.assertIsNone(packet.paper_status)
        self.assertEqual(packet.next_allowed_actions, ["create_action_intent"])
        self.assertFalse(packet.execution_allowed)

    def test_action_intent_only(self) -> None:
        """Chain with action intent but no downstream artifacts."""
        proposal_id = self._proposal_id()
        action_intent_id = self._insert_action_intent(proposal_id)

        packet = build_pretrade_packet(proposal_id, self.engine)

        self.assertIsNotNone(packet.action_draft)
        assert packet.action_draft is not None
        self.assertEqual(packet.action_draft.action_intent_id, action_intent_id)
        self.assertEqual(packet.action_draft.action_type, "reduce_exposure")
        self.assertEqual(packet.authority_findings, [])
        self.assertEqual(packet.preflight_status, "missing")
        self.assertIn("create_authority_binding", packet.next_allowed_actions)

    def test_authority_binding_present(self) -> None:
        """Chain with action intent + authority binding."""
        proposal_id = self._proposal_id()
        aid = self._insert_action_intent(proposal_id)
        self._insert_authority_binding(aid, proposal_id)

        packet = build_pretrade_packet(proposal_id, self.engine)

        self.assertIsNotNone(packet.action_draft)
        self.assertEqual(len(packet.authority_findings), 1)
        finding = packet.authority_findings[0]
        self.assertEqual(finding.author_type, "agent")
        self.assertEqual(finding.author_id, "test_agent")
        self.assertTrue(finding.allowed)
        self.assertEqual(packet.preflight_status, "pass")

    def test_authority_binding_denied(self) -> None:
        """When authority binding is not allowed, preflight_status is block."""
        proposal_id = self._proposal_id()
        aid = self._insert_action_intent(proposal_id)
        bid = f"ab_denied_{aid[-8:]}"
        write_records(
            [
                ActionIntentAuthorityBinding(
                    binding_id=bid,
                    action_intent_id=aid,
                    proposal_id=proposal_id,
                    author_type="agent",
                    author_id="bad_agent",
                    allowed=False,
                    deny_reasons=["agent_intent_missing_grant"],
                )
            ],
            engine=self.engine,
        )

        packet = build_pretrade_packet(proposal_id, self.engine)

        self.assertEqual(len(packet.authority_findings), 1)
        self.assertEqual(packet.preflight_status, "block")

    def test_partial_chain_through_simulation(self) -> None:
        """Chain through simulation, no plan beyond."""
        proposal_id = self._proposal_id()
        aid = self._insert_action_intent(proposal_id)
        self._insert_authority_binding(aid, proposal_id)
        self._insert_simulation(aid, proposal_id)

        packet = build_pretrade_packet(proposal_id, self.engine)

        self.assertIsNotNone(packet.simulation)
        assert packet.simulation is not None
        self.assertEqual(packet.simulation.scenario_mode, "descriptive_v0")
        self.assertEqual(packet.simulation.simulation_status, "complete")
        self.assertIn("create_trade_plan_candidate", packet.next_allowed_actions)
        self.assertIsNone(packet.plan)

    def test_complete_chain(self) -> None:
        """Full chain: intent → binding → simulation → plan → fit → gate → paper."""
        proposal_id = self._proposal_id()
        aid = self._insert_action_intent(proposal_id)
        self._insert_authority_binding(aid, proposal_id)
        sid = self._insert_simulation(aid, proposal_id)
        pid = self._insert_plan(aid, sid, proposal_id)
        self._insert_fit(pid, aid, sid, proposal_id)
        gid = self._insert_gate(pid, aid, sid, proposal_id)
        self._insert_paper_ticket(pid, gid, aid, sid, proposal_id)

        packet = build_pretrade_packet(proposal_id, self.engine)

        # Every section populated
        self.assertIsNotNone(packet.action_draft)
        self.assertEqual(len(packet.authority_findings), 1)
        self.assertEqual(packet.preflight_status, "pass")
        self.assertIsNotNone(packet.simulation)
        self.assertIsNotNone(packet.plan)
        self.assertIsNotNone(packet.objective_fit)
        self.assertIsNotNone(packet.approval)
        self.assertIsNotNone(packet.paper_status)

        # Check plan
        assert packet.plan is not None
        self.assertEqual(packet.plan.plan_direction, "reduce")

        # Check objective fit
        assert packet.objective_fit is not None
        self.assertEqual(packet.objective_fit.objective_alignment, "aligned")

        # Check approval
        assert packet.approval is not None
        self.assertEqual(
            packet.approval.review_decision,
            "allow_order_ticket_candidate_staging",
        )

        # Check paper
        assert packet.paper_status is not None
        self.assertEqual(packet.paper_status.side, "sell")
        self.assertEqual(packet.paper_status.order_type, "market")

        # execution_allowed is always False
        self.assertFalse(packet.execution_allowed)

        # next_allowed_actions should be empty for complete chain
        self.assertEqual(packet.next_allowed_actions, [])

    def test_execution_always_false(self) -> None:
        """execution_allowed is always False, even on complete chains."""
        proposal_id = self._proposal_id()
        aid = self._insert_action_intent(proposal_id)
        self._insert_authority_binding(aid, proposal_id)
        sid = self._insert_simulation(aid, proposal_id)
        pid = self._insert_plan(aid, sid, proposal_id)
        self._insert_fit(pid, aid, sid, proposal_id)
        gid = self._insert_gate(pid, aid, sid, proposal_id)
        self._insert_paper_ticket(pid, gid, aid, sid, proposal_id)

        packet = build_pretrade_packet(proposal_id, self.engine)

        # Must be False regardless of chain completeness
        self.assertFalse(packet.execution_allowed)
        # Type annotation says Literal[False], not bool
        self.assertIs(packet.execution_allowed, False)

    def test_non_existent_proposal(self) -> None:
        """Building a packet for a proposal that doesn't exist."""
        packet = build_pretrade_packet("nonexistent_proposal", self.engine)

        self.assertIsInstance(packet, PreTradePacket)
        self.assertEqual(packet.proposal_id, "nonexistent_proposal")
        self.assertIsNone(packet.action_draft)
        self.assertFalse(packet.execution_allowed)
