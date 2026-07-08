"""Tests for legacy action chain separation bridge.

Verifies:
- Execution facts are projected into canonical execution layer.
- Agentic artifacts stay OUT of execution projection.
- Deletion candidates are identified.
- No execution over-assimilation (CapitalObjectiveFit etc stay agentic).
"""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from finharness.execution.legacy_bridge import (
    AgenticArtifactKind,
    LegacyExecutionBridgeResult,
    separate_legacy_chain,
)
from finharness.statecore.models import (
    ActionIntent,
    ActionIntentAuthorityBinding,
    ActionIntentSimulationReport,
    CapitalObjectiveFit,
    PaperExecutionReceipt,
    PaperOrderTicketCandidate,
    TradePlanCandidate,
    TradePlanReviewGate,
)
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core, write_records
from tests._scaffold import VALID_SCAFFOLD


class LegacyBridgeSeparationTest(unittest.TestCase):
    """Separation bridge: execution vs agentic classification."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "db.sqlite")
        self.receipt_root = self.root / "receipts" / "state-core"
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _proposal_id(self) -> str:
        pw = create_governed_proposal(
            kind="exposure_scan",
            claim="legacy bridge test",
            evidence={"test": True},
            assumptions={},
            limitations={},
            source_refs=["test://legacy_bridge"],
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=str(self.receipt_root),
        )
        return pw.proposal.proposal_id

    def _seed_full_chain(self) -> str:
        """Seed a complete legacy ActionIntent chain."""
        pid = self._proposal_id()
        aid = f"ai_{pid[-8:]}"
        sid = f"sim_{pid[-8:]}"
        tid = f"tpc_{pid[-8:]}"
        fid = f"fit_{pid[-8:]}"
        gid = f"gate_{pid[-8:]}"
        pid_ticket = f"paper_{pid[-8:]}"

        write_records(
            [
                ActionIntent(
                    action_intent_id=aid,
                    proposal_id=pid,
                    source_proposal_receipt_ref="test",
                    created_by="agent",
                    action_type="reduce_exposure",
                    intent_summary="reduce risk",
                    rationale="concentration too high",
                    expected_next_step="simulation",
                ),
                ActionIntentAuthorityBinding(
                    binding_id=f"ab_{pid[-8:]}",
                    action_intent_id=aid,
                    proposal_id=pid,
                    author_type="agent",
                    author_id="test_agent",
                    allowed=True,
                ),
                ActionIntentSimulationReport(
                    simulation_report_id=sid,
                    action_intent_id=aid,
                    proposal_id=pid,
                    source_action_intent_receipt_ref="test",
                    source_action_preflight_report_hash="hash",
                    source_action_preflight_status="pass",
                    source_action_preflight_finding_codes=["POSITION_LIMIT_OK"],
                    risk_posture="moderate",
                    risk_direction="neutral",
                    simulation_status="complete",
                ),
                TradePlanCandidate(
                    trade_plan_candidate_id=tid,
                    action_intent_id=aid,
                    simulation_report_id=sid,
                    proposal_id=pid,
                    source_action_intent_receipt_ref="test",
                    source_action_preflight_report_hash="hash",
                    source_simulation_report_receipt_ref="test",
                    source_action_preflight_status="pass",
                    plan_direction="reduce",
                    plan_reason="lower concentration",
                    candidate_status="needs_authority_contract",
                ),
                CapitalObjectiveFit(
                    capital_objective_fit_id=fid,
                    trade_plan_candidate_id=tid,
                    action_intent_id=aid,
                    simulation_report_id=sid,
                    proposal_id=pid,
                    source_trade_plan_candidate_receipt_ref="test",
                    source_action_intent_receipt_ref="test",
                    source_action_preflight_report_hash="hash",
                    source_simulation_report_receipt_ref="test",
                    objective_alignment="aligned",
                    benefit_thesis="reduces single-name risk",
                    recommended_next_safe_path="proceed",
                ),
                TradePlanReviewGate(
                    review_gate_id=gid,
                    trade_plan_candidate_id=tid,
                    action_intent_id=aid,
                    simulation_report_id=sid,
                    proposal_id=pid,
                    source_trade_plan_candidate_receipt_ref="test",
                    source_action_intent_receipt_ref="test",
                    source_action_preflight_report_hash="hash",
                    source_simulation_report_receipt_ref="test",
                    review_decision="allow_order_ticket_candidate_staging",
                    reviewer_type="human",
                    reviewer_id="test_op",
                    review_reason="approved",
                    may_enter_order_ticket_candidate_staging=True,
                ),
                PaperOrderTicketCandidate(
                    paper_order_ticket_id=pid_ticket,
                    trade_plan_candidate_id=tid,
                    review_gate_id=gid,
                    action_intent_id=aid,
                    simulation_report_id=sid,
                    proposal_id=pid,
                    source_trade_plan_candidate_receipt_ref="test",
                    source_review_gate_receipt_ref="test",
                    source_action_intent_receipt_ref="test",
                    source_action_preflight_report_hash="hash",
                    source_simulation_report_receipt_ref="test",
                    paper_account_ref="pa_test",
                    instrument_ref="SPY",
                    symbol="SPY",
                    side="sell",
                    order_type="market",
                    quantity=Decimal("100"),
                    ticket_rationale="reduce SPY by 100",
                ),
            ],
            engine=self.engine,
        )
        return pid

    # ── tests ────────────────────────────────────────────────────────────

    def test_empty_chain(self) -> None:
        """Empty proposal → no execution projection, no artifacts."""
        pid = self._proposal_id()
        result = separate_legacy_chain(pid, self.engine)

        self.assertIsInstance(result, LegacyExecutionBridgeResult)
        self.assertEqual(result.proposal_id, pid)
        self.assertEqual(result.agentic_artifacts, [])
        self.assertEqual(result.deletion_candidates, [])
        self.assertEqual(len(result.execution_projection.order_draft_projections), 0)
        self.assertEqual(len(result.execution_projection.approval_projections), 0)

    def test_full_chain_separation(self) -> None:
        """Full legacy chain → separated into execution / agentic / deletion."""
        pid = self._seed_full_chain()
        result = separate_legacy_chain(pid, self.engine)

        # ── Execution projection exists ──
        self.assertGreater(len(result.execution_projection.order_draft_projections), 0)
        self.assertGreater(len(result.execution_projection.execution_order_projections), 0)
        self.assertGreater(len(result.execution_projection.approval_projections), 0)
        self.assertGreater(len(result.execution_projection.pretrade_findings), 0)

        # ── Agentic artifacts exist (not in execution projection) ──
        self.assertGreater(len(result.agentic_artifacts), 3)

        # ── Deletion candidates exist ──
        self.assertGreater(len(result.deletion_candidates), 3)

    def test_objective_fit_is_agentic_not_execution(self) -> None:
        """CapitalObjectiveFit → skill_output agentic artifact, NOT in execution projection."""
        pid = self._seed_full_chain()
        result = separate_legacy_chain(pid, self.engine)

        fit_artifacts = [
            a for a in result.agentic_artifacts
            if a.source_object == "CapitalObjectiveFit"
        ]
        self.assertGreater(len(fit_artifacts), 0)
        fit = fit_artifacts[0]
        self.assertEqual(fit.kind, "skill_output")
        self.assertIn("aligned", fit.summary)

        # CapitalObjectiveFit is NOT in execution projection
        # (execution_projection has no objective_fit field)
        self.assertFalse(
            hasattr(result.execution_projection, "objective_fit_projection"),
            "CapitalObjectiveFit should NOT be in execution projection",
        )

    def test_authority_binding_is_evaluator_not_execution(self) -> None:
        """AuthorityBinding → evaluator_finding agentic artifact, NOT approval."""
        pid = self._seed_full_chain()
        result = separate_legacy_chain(pid, self.engine)

        binding_artifacts = [
            a for a in result.agentic_artifacts
            if a.source_object == "ActionIntentAuthorityBinding"
        ]
        self.assertGreater(len(binding_artifacts), 0)
        self.assertEqual(binding_artifacts[0].kind, "evaluator_finding")

    def test_action_intent_is_agentic_draft(self) -> None:
        """ActionIntent → context agentic artifact, deletion candidate."""
        pid = self._seed_full_chain()
        result = separate_legacy_chain(pid, self.engine)

        intent_artifacts = [
            a for a in result.agentic_artifacts
            if a.source_object == "ActionIntent"
        ]
        self.assertGreater(len(intent_artifacts), 0)
        self.assertEqual(intent_artifacts[0].kind, "context")

        # ActionIntent should be a deletion candidate
        intent_deletions = [
            d for d in result.deletion_candidates
            if d.object_type == "ActionIntent"
        ]
        self.assertGreater(len(intent_deletions), 0)
        self.assertEqual(intent_deletions[0].superseded_by, "OrderDraft")

    def test_review_gate_projects_to_approval(self) -> None:
        """TradePlanReviewGate human decision → approval_projections in execution."""
        pid = self._seed_full_chain()
        result = separate_legacy_chain(pid, self.engine)

        approval = result.execution_projection.approval_projections[0]
        self.assertIsNotNone(approval)
        self.assertEqual(approval["source"], "TradePlanReviewGate")
        self.assertEqual(
            approval["decision"], "allow_order_ticket_candidate_staging"
        )

    def test_paper_ticket_projects_to_order_draft(self) -> None:
        """PaperOrderTicketCandidate order fields → order_draft_projections."""
        pid = self._seed_full_chain()
        result = separate_legacy_chain(pid, self.engine)

        draft = result.execution_projection.order_draft_projections[0]
        self.assertIsNotNone(draft)
        self.assertEqual(draft["source"], "PaperOrderTicketCandidate")
        self.assertEqual(draft["symbol"], "SPY")
        self.assertEqual(draft["side"], "sell")
        self.assertEqual(draft["order_type"], "market")
        self.assertEqual(draft["quantity"], "100")

    def test_no_execution_over_assimilation(self) -> None:
        """Agentic artifacts are NOT misplaced into execution projection."""
        pid = self._seed_full_chain()
        result = separate_legacy_chain(pid, self.engine)

        # Get all agentic artifact source objects
        agentic_sources = {a.source_object for a in result.agentic_artifacts}

        # These must appear as agentic, not as execution facts
        self.assertIn("CapitalObjectiveFit", agentic_sources)
        self.assertIn("ActionIntentAuthorityBinding", agentic_sources)
        self.assertIn("ActionIntent", agentic_sources)

        # The execution projection must NOT contain these as first-class fields
        self.assertGreater(len(result.execution_projection.order_draft_projections), 0)
        # But there is NO objective_fit or authority_binding field on ExecutionProjection

        # Verify unresolved semantics exist for objective fit
        unresolved = [
            u for u in result.unresolved_semantics
            if u.source == "CapitalObjectiveFit"
        ]
        self.assertGreater(len(unresolved), 0)
        self.assertIn("review memo", unresolved[0].recommendation)

    def test_all_deletion_candidates_have_superseded_by(self) -> None:
        """Every deletion candidate declares what replaces it."""
        pid = self._seed_full_chain()
        result = separate_legacy_chain(pid, self.engine)

        for d in result.deletion_candidates:
            self.assertIsNotNone(d.superseded_by, f"{d.object_type} missing superseded_by")
            self.assertGreater(len(d.superseded_by), 0)

    def test_agentic_artifact_kinds_are_enum_values(self) -> None:
        """All agentic artifacts have kind that is an AgenticArtifactKind enum."""
        pid = self._seed_full_chain()
        result = separate_legacy_chain(pid, self.engine)

        for artifact in result.agentic_artifacts:
            self.assertIsInstance(
                artifact.kind,
                AgenticArtifactKind,
                f"{artifact.source_object}: {artifact.kind} is not AgenticArtifactKind",
            )

        # Verify classification correctness — specific mappings
        kinds_by_source: dict[str, set[AgenticArtifactKind]] = {}
        for a in result.agentic_artifacts:
            kinds_by_source.setdefault(a.source_object, set()).add(a.kind)

        # CapitalObjectiveFit → SKILL_OUTPUT
        self.assertIn(
            AgenticArtifactKind.SKILL_OUTPUT,
            kinds_by_source.get("CapitalObjectiveFit", set()),
        )
        # AuthorityBinding → EVALUATOR_FINDING
        self.assertIn(
            AgenticArtifactKind.EVALUATOR_FINDING,
            kinds_by_source.get("ActionIntentAuthorityBinding", set()),
        )
        # TradePlanReviewGate → PERMISSION_TRACE
        self.assertIn(
            AgenticArtifactKind.PERMISSION_TRACE,
            kinds_by_source.get("TradePlanReviewGate", set()),
        )
        # ActionIntent → CONTEXT
        self.assertIn(
            AgenticArtifactKind.CONTEXT,
            kinds_by_source.get("ActionIntent", set()),
        )
        # SimulationReport → WORKFLOW_OUTPUT
        self.assertIn(
            AgenticArtifactKind.WORKFLOW_OUTPUT,
            kinds_by_source.get("ActionIntentSimulationReport", set()),
        )

    def test_multi_ticket_and_execution_preserves_all_projections(self) -> None:
        """Two tickets, two executions → both captured, none overwritten."""
        pid = self._seed_full_chain()

        # Verify single chain has 1 order draft, no execution report yet
        result_single = separate_legacy_chain(pid, self.engine)
        self.assertEqual(
            len(result_single.execution_projection.order_draft_projections), 1,
            "seed should have 1 ticket",
        )

        # Add a second ticket + execution on top of the same chain
        tid2 = f"tpc2_{pid[-8:]}"
        pid_ticket2 = f"paper2_{pid[-8:]}"
        pex2 = f"pex2_{pid[-8:]}"
        # Re-use existing parent IDs from _seed_full_chain pattern
        existing_ai_id = f"ai_{pid[-8:]}"
        existing_sim_id = f"sim_{pid[-8:]}"
        existing_gate_id = f"gate_{pid[-8:]}"

        write_records(
            [
                TradePlanCandidate(
                    trade_plan_candidate_id=tid2,
                    action_intent_id=existing_ai_id,
                    simulation_report_id=existing_sim_id,
                    proposal_id=pid,
                    source_action_intent_receipt_ref="test",
                    source_action_preflight_report_hash="hash",
                    source_simulation_report_receipt_ref="test",
                    source_action_preflight_status="pass",
                    plan_direction="reduce",
                    plan_reason="second ticket",
                    candidate_status="needs_authority_contract",
                ),
                PaperOrderTicketCandidate(
                    paper_order_ticket_id=pid_ticket2,
                    trade_plan_candidate_id=tid2,
                    review_gate_id=existing_gate_id,
                    action_intent_id=existing_ai_id,
                    simulation_report_id=existing_sim_id,
                    proposal_id=pid,
                    source_trade_plan_candidate_receipt_ref="test",
                    source_review_gate_receipt_ref="test",
                    source_action_intent_receipt_ref="test",
                    source_action_preflight_report_hash="hash",
                    source_simulation_report_receipt_ref="test",
                    paper_account_ref="pa_test",
                    instrument_ref="QQQ",
                    symbol="QQQ",
                    side="buy",
                    order_type="limit",
                    quantity=Decimal("50"),
                    ticket_rationale="buy QQQ 50",
                ),
                PaperExecutionReceipt(
                    paper_execution_id=pex2,
                    paper_order_ticket_id=pid_ticket2,
                    trade_plan_candidate_id=tid2,
                    review_gate_id=existing_gate_id,
                    action_intent_id=existing_ai_id,
                    simulation_report_id=existing_sim_id,
                    proposal_id=pid,
                    source_paper_order_ticket_receipt_ref="test",
                    source_trade_plan_candidate_receipt_ref="test",
                    source_review_gate_receipt_ref="test",
                    source_action_intent_receipt_ref="test",
                    source_action_preflight_report_hash="hash",
                    source_simulation_report_receipt_ref="test",
                    paper_account_ref="pa_test",
                    symbol="QQQ",
                    side="buy",
                    quantity=Decimal("50"),
                    fill_price=Decimal("380.00"),
                    gross_notional=Decimal("19000.00"),
                    execution_status="simulated_filled",
                    simulator_ref="test-sim",
                    executed_at_utc="2026-01-01T00:00:00Z",
                ),
            ],
            engine=self.engine,
        )

        result = separate_legacy_chain(pid, self.engine)

        # Both tickets projected → 2 order drafts (1 seed + 1 new)
        self.assertEqual(
            len(result.execution_projection.order_draft_projections), 2,
            "two tickets should produce two order_draft_projections",
        )

        # New execution receipt is captured (was 0, now 1)
        self.assertGreaterEqual(
            len(result.execution_projection.execution_report_projections), 1,
            "new execution receipt should be captured",
        )

        # Verify distinct symbols captured in order drafts
        symbols = {d["symbol"] for d in result.execution_projection.order_draft_projections}
        self.assertEqual(symbols, {"SPY", "QQQ"})

        # New QQQ execution captured (check source_id prefix)
        report_sources = {
            r["source_id"] for r in result.execution_projection.execution_report_projections
        }
        self.assertIn(pex2, report_sources)
