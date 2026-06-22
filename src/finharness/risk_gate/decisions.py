"""Risk-gate decision classification and construction."""

from __future__ import annotations

from uuid import uuid4

from finharness.portfolio_risk import RiskfolioAllocationSummary
from finharness.proposal import ProposalCandidate, ProposalSnapshot
from finharness.risk_gate._constants import RiskGateDecisionValue
from finharness.risk_gate._util import now_utc
from finharness.risk_gate.context import risk_context_for_candidate
from finharness.risk_gate.controls import (
    authorization_for_risk_context,
    candidate_checks,
    restricted_symbol_for_candidate,
    tradability_for_candidate,
)
from finharness.risk_gate.models import RiskGateCheck, RiskGateContext, RiskGateDecision


def classify_decision(
    *,
    candidate: ProposalCandidate,
    checks: list[RiskGateCheck],
) -> RiskGateDecisionValue:
    failed = [item for item in checks if item.status == "failed"]
    failed_types = {item.check_type for item in failed}
    if candidate.action_type == "avoid_or_reject":
        return "rejected"
    if {"proposal_quality_check", "paper_or_live_permission_check"} & failed_types:
        return "blocked"
    if {
        "mandate_check",
        "instrument_permission_check",
        "restricted_symbol_check",
        "max_notional_check",
        "concentration_check",
        "drawdown_state_check",
        "behavior_reset_check",
        "authorization_check",
        "order_language_check",
    } & failed_types:
        return "blocked"
    if "human_review_check" in failed_types:
        return "needs_human_review"
    if failed:
        return "needs_more_evidence"
    if candidate.action_type == "paper_trade_candidate":
        return "approved_for_paper_review"
    return "needs_more_evidence"


def build_risk_gate_decision(
    *,
    proposal_snapshot: ProposalSnapshot,
    candidate: ProposalCandidate,
    context: RiskGateContext,
    allocation_summary: RiskfolioAllocationSummary | None = None,
) -> RiskGateDecision:
    effective_context = risk_context_for_candidate(
        context=context,
        candidate=candidate,
        allocation_summary=allocation_summary,
    )
    authorization_decision = authorization_for_risk_context(effective_context)
    restricted_symbol_decision = restricted_symbol_for_candidate(
        context=effective_context,
        candidate=candidate,
    )
    tradability_decision = tradability_for_candidate(
        context=effective_context,
        candidate=candidate,
    )
    checks = candidate_checks(
        proposal_snapshot=proposal_snapshot,
        candidate=candidate,
        context=effective_context,
        allocation_summary=allocation_summary,
        authorization_decision=authorization_decision,
        restricted_symbol_decision=restricted_symbol_decision,
        tradability_decision=tradability_decision,
    )
    decision = classify_decision(candidate=candidate, checks=checks)
    failed_checks = [item for item in checks if item.status == "failed"]
    blocking_reasons = [item.reason for item in failed_checks if item.blocking]
    required_remediations = [
        f"Resolve {item.check_type}: {item.reason}" for item in failed_checks
    ]
    paper_review_allowed = decision == "approved_for_paper_review"
    return RiskGateDecision(
        decision_id=f"rgdec_{uuid4().hex[:12]}",
        proposal_id=candidate.proposal_id,
        symbol=candidate.symbol,
        action_type=candidate.action_type,
        decision=decision,
        checks=checks,
        blocking_reasons=blocking_reasons,
        required_remediations=required_remediations,
        authorization=authorization_decision,
        restricted_symbol=restricted_symbol_decision,
        tradability=tradability_decision,
        paper_review_allowed=paper_review_allowed,
        live_execution_allowed=False,
        human_review_required=True,
        created_at_utc=now_utc(),
    )


def build_risk_gate_decisions(
    *,
    proposal_snapshot: ProposalSnapshot,
    context: RiskGateContext,
    allocation_summary: RiskfolioAllocationSummary | None = None,
) -> list[RiskGateDecision]:
    return [
        build_risk_gate_decision(
            proposal_snapshot=proposal_snapshot,
            candidate=candidate,
            context=context,
            allocation_summary=allocation_summary,
        )
        for candidate in proposal_snapshot.candidates
    ]
