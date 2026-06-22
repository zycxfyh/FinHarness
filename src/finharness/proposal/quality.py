"""Proposal quality gates and risk-gate handoff helpers."""

from __future__ import annotations

from finharness.proposal._util import candidate_text_for_guard, find_blocked_language
from finharness.proposal.models import ProposalCandidate, ProposalQuality
from finharness.validation import ValidationSnapshot


def missing_proposal_fields(candidate: ProposalCandidate) -> list[str]:
    missing: list[str] = []
    if not candidate.source_validation_result_ids:
        missing.append("source_validation_result_ids")
    if not candidate.evidence_summary:
        missing.append("evidence_summary")
    if not candidate.validation_summary:
        missing.append("validation_summary")
    if not candidate.portfolio_role:
        missing.append("portfolio_role")
    if not candidate.invalidation_triggers:
        missing.append("invalidation_triggers")
    if not candidate.risk_gate_request.required_checks:
        missing.append("risk_gate_handoff")
    if not candidate.constraint_notes:
        missing.append("constraint_notes")
    if not candidate.alternatives_considered:
        missing.append("alternatives_considered")
    if not candidate.do_nothing_case:
        missing.append("do_nothing_case")
    if not candidate.risk_gate_request.human_review_required:
        missing.append("human_review_required")
    return missing


def build_proposal_quality(
    *,
    validation_snapshot: ValidationSnapshot,
    candidates: list[ProposalCandidate],
) -> ProposalQuality:
    missing_required_fields: dict[str, list[str]] = {}
    blocked_language_hits: dict[str, list[str]] = {}
    for candidate in candidates:
        missing = missing_proposal_fields(candidate)
        if missing:
            missing_required_fields[candidate.proposal_id] = missing
        hits = find_blocked_language(candidate_text_for_guard(candidate))
        if hits:
            blocked_language_hits[candidate.proposal_id] = hits

    validation_snapshot_linked = bool(validation_snapshot.validation_snapshot_id)
    validation_quality_ok = bool(validation_snapshot.quality.ok)
    evidence_summary_present = all(candidate.evidence_summary for candidate in candidates)
    validation_summary_present = all(candidate.validation_summary for candidate in candidates)
    portfolio_role_present = all(candidate.portfolio_role for candidate in candidates)
    invalidation_triggers_present = all(candidate.invalidation_triggers for candidate in candidates)
    risk_handoff_present = all(
        candidate.risk_gate_request.required_checks for candidate in candidates
    )
    constraints_present = all(candidate.constraint_notes for candidate in candidates)
    alternatives_considered = all(candidate.alternatives_considered for candidate in candidates)
    do_nothing_case_present = all(candidate.do_nothing_case for candidate in candidates)
    no_blocked_language = not blocked_language_hits
    no_execution_authority = all(
        not candidate.risk_gate_request.execution_intent.lower().startswith("execute")
        and "no execution" in candidate.risk_gate_request.execution_intent.lower()
        for candidate in candidates
    )
    no_final_sizing = all(
        "no final sizing" in candidate.risk_gate_request.sizing_intent.lower()
        for candidate in candidates
    )
    human_review_required = all(
        candidate.risk_gate_request.human_review_required for candidate in candidates
    )
    notes: list[str] = []
    if not candidates:
        notes.append("no proposal candidates were created")

    ok = (
        bool(candidates)
        and validation_snapshot_linked
        and validation_quality_ok
        and evidence_summary_present
        and validation_summary_present
        and portfolio_role_present
        and invalidation_triggers_present
        and risk_handoff_present
        and constraints_present
        and alternatives_considered
        and do_nothing_case_present
        and no_execution_authority
        and no_blocked_language
        and no_final_sizing
        and human_review_required
        and not missing_required_fields
    )
    return ProposalQuality(
        ok=ok,
        candidate_count=len(candidates),
        validation_snapshot_linked=validation_snapshot_linked,
        validation_quality_ok=validation_quality_ok,
        evidence_summary_present=evidence_summary_present,
        validation_summary_present=validation_summary_present,
        portfolio_role_present=portfolio_role_present,
        invalidation_triggers_present=invalidation_triggers_present,
        risk_handoff_present=risk_handoff_present,
        constraints_present=constraints_present,
        alternatives_considered=alternatives_considered,
        do_nothing_case_present=do_nothing_case_present,
        no_execution_authority=no_execution_authority,
        no_order_language=no_blocked_language,
        no_final_sizing=no_final_sizing,
        human_review_required=human_review_required,
        missing_required_fields=missing_required_fields,
        blocked_language_hits=blocked_language_hits,
        notes=notes,
    )


def risk_gate_handoff(candidates: list[ProposalCandidate]) -> list[str]:
    return [
        (
            f"{candidate.proposal_id}: {candidate.action_type} for {candidate.symbol}; "
            "independent risk gate required before any further action."
        )
        for candidate in candidates
    ]


def snapshot_review_questions(candidates: list[ProposalCandidate]) -> list[str]:
    questions = [
        "Which proposal has the weakest validation evidence?",
        "Which do-nothing case is strongest?",
        "Which risk-gate check is most likely to block the candidate?",
        "Did any proposal language imply execution authority?",
    ]
    if any(candidate.action_type == "paper_trade_candidate" for candidate in candidates):
        questions.append("Which paper candidate should be downgraded to watch-only?")
    return questions
