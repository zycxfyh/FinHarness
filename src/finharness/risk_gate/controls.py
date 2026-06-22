"""Risk-gate control checks."""

from __future__ import annotations

from finharness.authorization import AuthorizationDecision, authorize
from finharness.portfolio_risk import RiskfolioAllocationSummary
from finharness.proposal import ProposalCandidate, ProposalSnapshot
from finharness.restricted_symbols import (
    RestrictedSymbolDecision,
    TradabilityDecision,
    is_restricted,
    tradability_for_symbol,
)
from finharness.risk_gate._util import check, find_blocked_language
from finharness.risk_gate.context import riskfolio_concentration_evidence_refs
from finharness.risk_gate.models import RiskGateCheck, RiskGateContext


def authorization_for_risk_context(context: RiskGateContext) -> AuthorizationDecision:
    return authorize(
        operator_id=context.operator_id.strip(),
        account_id=context.account_id.strip(),
        environment=context.authorization_environment,
        scope=context.authorization_scope.strip(),
        registry_path=context.authorization_registry_ref,
    )


def restricted_symbol_for_candidate(
    *,
    context: RiskGateContext,
    candidate: ProposalCandidate,
) -> RestrictedSymbolDecision:
    return is_restricted(
        candidate.symbol,
        restricted_list_path=context.restricted_symbols_ref,
    )


def tradability_for_candidate(
    *,
    context: RiskGateContext,
    candidate: ProposalCandidate,
) -> TradabilityDecision:
    return tradability_for_symbol(
        candidate.symbol,
        provider=context.tradability_provider,
        receipt_ref=context.tradability_receipt_ref,
        manual_tradability=context.manual_tradability,
    )


def candidate_checks(
    *,
    proposal_snapshot: ProposalSnapshot,
    candidate: ProposalCandidate,
    context: RiskGateContext,
    allocation_summary: RiskfolioAllocationSummary | None = None,
    authorization_decision: AuthorizationDecision | None = None,
    restricted_symbol_decision: RestrictedSymbolDecision | None = None,
    tradability_decision: TradabilityDecision | None = None,
) -> list[RiskGateCheck]:
    refs = [proposal_snapshot.payload_ref, proposal_snapshot.receipt_ref]
    candidate_language_hits = find_blocked_language(candidate.rationale)
    authorization = authorization_decision or authorization_for_risk_context(context)
    restricted_symbol = restricted_symbol_decision or restricted_symbol_for_candidate(
        context=context,
        candidate=candidate,
    )
    tradability = tradability_decision or tradability_for_candidate(
        context=context,
        candidate=candidate,
    )
    restricted_check_passed = (
        not restricted_symbol.restricted and tradability.allowed
    )
    restricted_reason = (
        "symbol is not restricted and provider tradability evidence allows review"
        if restricted_check_passed
        else "; ".join(
            reason
            for reason in [
                f"restricted symbol: {restricted_symbol.reason}"
                if restricted_symbol.restricted
                else "",
                f"provider tradability: {tradability.reason}"
                if not tradability.allowed
                else "",
            ]
            if reason
        )
    )
    return [
        check(
            proposal_id=candidate.proposal_id,
            check_type="proposal_quality_check",
            passed=proposal_snapshot.quality.ok,
            reason="ProposalSnapshot quality must pass before risk review can continue.",
            evidence_refs=refs,
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="source_linkage_check",
            passed=bool(
                candidate.source_validation_snapshot_id
                and candidate.source_validation_result_ids
            ),
            reason="Candidate must link back to validation snapshot and result ids.",
            evidence_refs=refs,
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="mandate_check",
            passed=bool(context.mandate_id and context.mandate_text),
            reason="Mandate context must be present for any risk-gate decision.",
            evidence_refs=[context.mandate_id],
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="instrument_permission_check",
            passed=(
                candidate.symbol in context.allowed_symbols
                and candidate.action_type in context.allowed_action_types
            ),
            reason="Symbol and action type must be allowed by the risk context.",
            evidence_refs=[context.mandate_id],
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="restricted_symbol_check",
            passed=restricted_check_passed,
            reason=restricted_reason,
            evidence_refs=[
                *restricted_symbol.evidence_refs,
                *tradability.evidence_refs,
            ],
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="paper_or_live_permission_check",
            passed=(
                context.requested_execution_mode != "live"
                and not context.live_execution_allowed
            ),
            reason="Live mode request is outside the MVP permission boundary.",
            evidence_refs=[context.mandate_id],
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="max_notional_check",
            passed=context.requested_notional <= context.max_paper_notional,
            reason="Requested paper notional must stay within configured cap.",
            evidence_refs=[context.mandate_id],
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="concentration_check",
            passed=(
                context.requested_symbol_concentration_pct
                <= context.max_symbol_concentration_pct
            ),
            reason="Requested symbol concentration must stay within configured cap.",
            evidence_refs=[
                context.mandate_id,
                *riskfolio_concentration_evidence_refs(
                    allocation_summary=allocation_summary,
                    symbol=candidate.symbol,
                    requested_concentration_pct=(
                        context.requested_symbol_concentration_pct
                    ),
                    max_symbol_concentration_pct=context.max_symbol_concentration_pct,
                ),
            ],
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="liquidity_check",
            passed=context.liquidity_evidence_present,
            reason="Liquidity evidence must be present before paper review approval.",
            evidence_refs=refs,
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="drawdown_state_check",
            passed=(
                context.drawdown_pct > context.hard_stop_drawdown_pct
                and context.consecutive_losses < context.hard_stop_consecutive_losses
            ),
            reason="Drawdown and consecutive-loss state must not trip hard stop.",
            evidence_refs=[context.mandate_id],
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="behavior_reset_check",
            passed=not context.behavior_reset_required,
            reason="Behavior reset state must not require stopping the workflow.",
            evidence_refs=[context.mandate_id],
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="scenario_check",
            passed=context.scenario_review_present and bool(candidate.scenario_notes),
            reason="Scenario notes must be present before risk-gate approval.",
            evidence_refs=refs,
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="authorization_check",
            passed=authorization.allowed,
            reason=authorization.reason,
            evidence_refs=[
                ref
                for ref in [
                    authorization.registry_ref,
                    authorization.registry_version,
                    f"operator:{authorization.operator_id}",
                    f"account:{authorization.account_id}",
                    f"environment:{authorization.environment}",
                    f"scope:{authorization.scope}",
                ]
                if ref
            ],
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="order_language_check",
            passed=not candidate_language_hits,
            reason="Candidate rationale must not contain restricted routing language.",
            evidence_refs=refs,
            blocked_language_hits=candidate_language_hits,
        ),
        check(
            proposal_id=candidate.proposal_id,
            check_type="human_review_check",
            passed=(
                context.human_review_attested
                and candidate.risk_gate_request.human_review_required
            ),
            reason="Human review attestation is required before paper review approval.",
            evidence_refs=[context.mandate_id],
        ),
    ]
