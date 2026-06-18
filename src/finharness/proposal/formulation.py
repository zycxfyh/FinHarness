"""Proposal candidate formulation helpers."""

from __future__ import annotations

from uuid import uuid4

from finharness.proposal._constants import STRUCTURAL_READY_RESULTS, ActionType, ProposalStatus
from finharness.proposal._util import now_utc
from finharness.proposal.models import ProposalCandidate, RiskGateRequest
from finharness.proposal.providers import NullProposalDraftProvider, ProposalDraftProvider
from finharness.validation import ValidationCheckResult, ValidationSnapshot


def group_results_by_hypothesis(
    validation_snapshot: ValidationSnapshot,
) -> dict[str, list[ValidationCheckResult]]:
    grouped: dict[str, list[ValidationCheckResult]] = {}
    for result in validation_snapshot.results:
        grouped.setdefault(result.hypothesis_id, []).append(result)
    return grouped


def classify_action_type(results: list[ValidationCheckResult]) -> ActionType:
    authority_results = [
        result for result in results if result.check_type != "backtest"
    ]
    values = [result.result for result in authority_results]
    structural_ready = sum(1 for value in values if value in STRUCTURAL_READY_RESULTS)
    not_testable = values.count("not_testable")
    disconfirmed = values.count("disconfirmed") + values.count("weakened")
    if disconfirmed:
        return "avoid_or_reject"
    if not_testable > structural_ready:
        return "research_more"
    if structural_ready >= 2 and not_testable <= 1:
        return "paper_trade_candidate"
    return "watch_only"


def status_for_action(action_type: ActionType) -> ProposalStatus:
    if action_type == "avoid_or_reject":
        return "rejected_before_risk"
    if action_type in {"research_more", "watch_only"}:
        return "needs_more_research"
    return "draft_for_risk_review"


def result_ids(results: list[ValidationCheckResult]) -> list[str]:
    return [result.check_id for result in results]


def summary_counts(results: list[ValidationCheckResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.result] = counts.get(result.result, 0) + 1
    return counts


def symbol_for_results(results: list[ValidationCheckResult], snapshot: ValidationSnapshot) -> str:
    job_by_id = {job.validation_job_id: job for job in snapshot.jobs}
    if results:
        job = job_by_id.get(results[0].validation_job_id)
        if job:
            return job.symbol
    return "UNKNOWN"


def invalidation_from_results(results: list[ValidationCheckResult]) -> list[str]:
    triggers = []
    for result in results:
        if result.check_type == "disconfirmation":
            observation = result.metrics.get("disconfirming_observation")
            if observation:
                triggers.append(str(observation))
    if not triggers:
        triggers.append("Risk gate cannot map disconfirmation evidence to the candidate.")
    return triggers


def constraints_for_candidate(action_type: ActionType) -> list[str]:
    constraints = [
        "Risk Gate must review mandate, concentration, liquidity, and drawdown state.",
        "This proposal creates no broker, exchange, or order instruction.",
        "Human review is required before any risk approval can be requested.",
    ]
    if action_type == "paper_trade_candidate":
        constraints.append("Paper-trade review only; live execution is out of scope.")
    return constraints


def build_risk_gate_request(proposal_id: str) -> RiskGateRequest:
    return RiskGateRequest(
        request_id=f"riskreq_{uuid4().hex[:12]}",
        proposal_id=proposal_id,
        required_checks=[
            "mandate_check",
            "max_notional_check",
            "concentration_check",
            "liquidity_check",
            "drawdown_state_check",
            "behavior_reset_check",
            "paper_or_live_permission_check",
        ],
        risk_budget_request="request independent risk-gate budget review only",
        sizing_intent="risk gate sizing review only; no final sizing",
        execution_intent="no execution; independent risk gate required",
        human_review_required=True,
    )


def formulate_proposal_candidate(
    *,
    validation_snapshot: ValidationSnapshot,
    hypothesis_id: str,
    results: list[ValidationCheckResult],
    draft_provider: ProposalDraftProvider | None = None,
) -> ProposalCandidate:
    provider = draft_provider or NullProposalDraftProvider()
    draft = provider.draft(results)
    proposal_id = f"prop_{uuid4().hex[:12]}"
    action_type = classify_action_type(results)
    counts = summary_counts(results)
    symbol = symbol_for_results(results, validation_snapshot)
    portfolio_role = (
        "proposal review candidate for research/paper workflow"
        if action_type == "paper_trade_candidate"
        else "research governance candidate"
    )
    evidence_summary = (
        f"Validation evidence for {hypothesis_id} contains "
        f"{', '.join(f'{key}:{value}' for key, value in sorted(counts.items()))}."
    )
    validation_summary = (
        "Layer 6 evidence is a validation package, not proof of alpha or permission."
    )
    expected_benefit = (
        "Clarify whether the validated hypothesis deserves independent risk review."
    )
    candidate = ProposalCandidate(
        proposal_id=proposal_id,
        source_validation_snapshot_id=validation_snapshot.validation_snapshot_id,
        source_validation_result_ids=result_ids(results),
        source_hypothesis_ids=[hypothesis_id],
        symbol=symbol,
        action_type=str(draft.get("action_type") or action_type),
        portfolio_role=str(draft.get("portfolio_role") or portfolio_role),
        rationale=str(
            draft.get("rationale")
            or f"Validation evidence is sufficient to create a {action_type} for review."
        ),
        evidence_summary=str(draft.get("evidence_summary") or evidence_summary),
        validation_summary=str(draft.get("validation_summary") or validation_summary),
        expected_benefit=str(draft.get("expected_benefit") or expected_benefit),
        key_risks=list(
            draft.get("key_risks")
            or [
                "Validation MVP may lack empirical event-window returns.",
                "Benchmark or factor context may explain the apparent signal.",
                "Disconfirmation items may remain untested.",
            ]
        ),
        invalidation_triggers=list(
            draft.get("invalidation_triggers") or invalidation_from_results(results)
        ),
        time_horizon=str(draft.get("time_horizon") or "inherits hypothesis horizon"),
        benchmark_context=str(draft.get("benchmark_context") or "SPY and QQQ context required"),
        scenario_notes=list(
            draft.get("scenario_notes")
            or [
                "If broad index context explains the move, the candidate weakens.",
                "If later source evidence contradicts the mechanism, the candidate weakens.",
            ]
        ),
        constraint_notes=list(
            draft.get("constraint_notes") or constraints_for_candidate(action_type)
        ),
        risk_gate_request=build_risk_gate_request(proposal_id),
        alternatives_considered=list(
            draft.get("alternatives_considered")
            or ["do nothing", "watch only", "request more validation evidence"]
        ),
        do_nothing_case=str(
            draft.get("do_nothing_case")
            or (
                "Do nothing if risk gate cannot verify mandate, context, "
                "and disconfirmation coverage."
            )
        ),
        status=status_for_action(action_type),
        draft_provider=provider.provider_name,
        draft_ref=draft.get("draft_ref"),
        created_at_utc=now_utc(),
    )
    return candidate


def build_proposal_candidates(
    *,
    validation_snapshot: ValidationSnapshot,
    draft_provider: ProposalDraftProvider | None = None,
) -> list[ProposalCandidate]:
    if not validation_snapshot.quality.ok:
        return []
    grouped = group_results_by_hypothesis(validation_snapshot)
    return [
        formulate_proposal_candidate(
            validation_snapshot=validation_snapshot,
            hypothesis_id=hypothesis_id,
            results=results,
            draft_provider=draft_provider,
        )
        for hypothesis_id, results in grouped.items()
    ]
