"""Risk-gate quality, persistence, and top-level bundle builder."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.market_data import display_path, sha256_text
from finharness.portfolio_risk import RiskfolioAllocationSummary
from finharness.proposal import ProposalSnapshot
from finharness.risk_gate._util import (
    decision_text_for_guard,
    find_blocked_language,
    now_utc,
    write_json,
)
from finharness.risk_gate.context import (
    normalize_allocation_summary,
    representative_risk_context,
)
from finharness.risk_gate.decisions import build_risk_gate_decisions
from finharness.risk_gate.models import (
    RiskGateBundle,
    RiskGateContext,
    RiskGateDecision,
    RiskGateLineage,
    RiskGateQuality,
    RiskGateReceipt,
    RiskGateSnapshot,
    RiskGateSourceSpec,
)


def risk_gate_storage_roots() -> tuple[Path, Path]:
    from finharness import risk_gate as risk_gate_package

    return (
        risk_gate_package.RISK_GATE_NORMALIZED_ROOT,
        risk_gate_package.RISK_GATE_RECEIPT_ROOT,
    )

def build_risk_gate_quality(
    *,
    proposal_snapshot: ProposalSnapshot,
    context: RiskGateContext,
    decisions: list[RiskGateDecision],
    lineage_complete: bool = True,
    receipt_written: bool = True,
) -> RiskGateQuality:
    missing_required_fields: dict[str, list[str]] = {}
    blocked_language_hits: dict[str, list[str]] = {}
    for decision in decisions:
        missing: list[str] = []
        if not decision.checks:
            missing.append("checks")
        if not decision.execution_intent:
            missing.append("execution_intent")
        if not decision.sizing_intent:
            missing.append("sizing_intent")
        if decision.human_review_required is not True:
            missing.append("human_review_required")
        if missing:
            missing_required_fields[decision.decision_id] = missing
        hits = find_blocked_language(decision_text_for_guard(decision))
        for item in decision.checks:
            hits.extend(item.blocked_language_hits)
        if hits:
            blocked_language_hits[decision.decision_id] = sorted(set(hits))

    proposal_snapshot_linked = bool(proposal_snapshot.proposal_snapshot_id)
    proposal_quality_ok = bool(proposal_snapshot.quality.ok)
    candidate_count = proposal_snapshot.candidate_count
    decision_count = len(decisions)
    decision_count_matches_candidate_count = decision_count == candidate_count
    all_decisions_have_checks = all(decision.checks for decision in decisions)
    hard_blocks_enforced = all(
        decision.decision != "approved_for_paper_review"
        for decision in decisions
        if any(check.blocking for check in decision.checks)
    )
    mandate_present = bool(context.mandate_id and context.mandate_text)
    permission_boundary_present = (
        not context.live_execution_allowed
        and all(not decision.live_execution_allowed for decision in decisions)
    )
    human_review_required = all(decision.human_review_required for decision in decisions)
    no_order_language = not blocked_language_hits
    no_live_execution_authority = all(
        not decision.live_execution_allowed
        and "no execution" in decision.execution_intent.lower()
        for decision in decisions
    )
    no_final_sizing = all(
        "no final sizing" in decision.sizing_intent.lower()
        for decision in decisions
    )
    notes: list[str] = []
    if not decisions:
        notes.append("no risk-gate decisions were created")

    ok = (
        bool(decisions)
        and proposal_snapshot_linked
        and proposal_quality_ok
        and decision_count_matches_candidate_count
        and all_decisions_have_checks
        and hard_blocks_enforced
        and mandate_present
        and permission_boundary_present
        and human_review_required
        and no_order_language
        and no_live_execution_authority
        and no_final_sizing
        and lineage_complete
        and receipt_written
        and not missing_required_fields
    )
    return RiskGateQuality(
        ok=ok,
        candidate_count=candidate_count,
        decision_count=decision_count,
        proposal_snapshot_linked=proposal_snapshot_linked,
        proposal_quality_ok=proposal_quality_ok,
        decision_count_matches_candidate_count=decision_count_matches_candidate_count,
        all_decisions_have_checks=all_decisions_have_checks,
        hard_blocks_enforced=hard_blocks_enforced,
        mandate_present=mandate_present,
        permission_boundary_present=permission_boundary_present,
        human_review_required=human_review_required,
        no_order_language=no_order_language,
        no_live_execution_authority=no_live_execution_authority,
        no_final_sizing=no_final_sizing,
        lineage_complete=lineage_complete,
        receipt_written=receipt_written,
        missing_required_fields=missing_required_fields,
        blocked_language_hits=blocked_language_hits,
        notes=notes,
    )


def execution_handoff(decisions: list[RiskGateDecision]) -> list[str]:
    handoff = []
    for decision in decisions:
        if decision.decision == "approved_for_paper_review":
            handoff.append(
                f"{decision.decision_id}: {decision.symbol} approved for paper "
                "review only; execution layer still required."
            )
    return handoff


def snapshot_review_questions(decisions: list[RiskGateDecision]) -> list[str]:
    questions = [
        "Which candidate was closest to a hard block?",
        "Which risk-gate threshold should be reviewed by a human?",
        "Did any decision imply live execution authority?",
        "Which paper-review approval should be downgraded?",
    ]
    if any(decision.decision == "blocked" for decision in decisions):
        questions.append("Which blocked candidate needs a postmortem?")
    return questions


def persist_risk_gate_bundle(
    *,
    source: RiskGateSourceSpec,
    input_proposal_snapshot: ProposalSnapshot,
    context: RiskGateContext,
    decisions: list[RiskGateDecision],
) -> RiskGateBundle:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    snapshot_id = f"rgates_{stamp}_{suffix}"
    receipt_id = f"receipt_{snapshot_id}"
    normalized_root, receipt_root = risk_gate_storage_roots()
    output_ref = normalized_root / f"{snapshot_id}.json"
    receipt_ref = receipt_root / f"{receipt_id}.json"
    quality = build_risk_gate_quality(
        proposal_snapshot=input_proposal_snapshot,
        context=context,
        decisions=decisions,
    )
    output_payload = {
        "risk_gate_snapshot_id": snapshot_id,
        "input_proposal_snapshot_id": input_proposal_snapshot.proposal_snapshot_id,
        "context": context.model_dump(mode="json"),
        "decisions": [decision.model_dump(mode="json") for decision in decisions],
    }
    output_hash = sha256_text(
        json.dumps(output_payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    lineage = RiskGateLineage(
        source=source,
        input_proposal_snapshot_id=input_proposal_snapshot.proposal_snapshot_id,
        input_proposal_receipt_ref=input_proposal_snapshot.receipt_ref,
        proposal_ids=[candidate.proposal_id for candidate in input_proposal_snapshot.candidates],
        proposal_transform_version=input_proposal_snapshot.lineage.transform_version,
        method=source.method,
        model_provider=source.llm_provider if source.llm_enabled else None,
        prompt_template_version=source.template_version,
        computed_at_utc=now_utc(),
        output_hash=output_hash,
        output_ref=display_path(output_ref),
    )
    snapshot = RiskGateSnapshot(
        risk_gate_snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        input_proposal_snapshot_id=input_proposal_snapshot.proposal_snapshot_id,
        universe=input_proposal_snapshot.universe,
        candidate_count=input_proposal_snapshot.candidate_count,
        decision_count=len(decisions),
        context=context,
        decisions=decisions,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(output_ref),
        receipt_ref=display_path(receipt_ref),
        execution_allowed=False,
        execution_handoff=execution_handoff(decisions),
        review_questions=snapshot_review_questions(decisions),
    )
    receipt = RiskGateReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source_input": "RiskGateSourceSpec + ProposalSnapshot + RiskGateContext",
            "proposal_quality": "ProposalSnapshot quality must pass",
            "mandate": "mandate and instrument permissions required",
            "limits": "paper notional and concentration caps checked",
            "drawdown_behavior": "drawdown and behavior hard stops checked",
            "decision": "approve paper review, block, reject, or request evidence",
            "quality": "hard blocks, no live execution, no final sizing",
            "lineage": "ProposalSnapshot refs, proposal ids, output hash/ref",
            "snapshot": "RiskGateSnapshot",
            "receipt": "RiskGateReceipt",
            "consumer_handoff": "review or future execution layer only",
        },
        snapshot=snapshot,
        status="ok" if quality.ok else "warning",
    )
    write_json(output_ref, output_payload)
    write_json(receipt_ref, receipt.model_dump(mode="json"))
    return RiskGateBundle(
        source=source,
        input_proposal_snapshot=input_proposal_snapshot,
        context=context,
        decisions=decisions,
        quality=quality,
        lineage=lineage,
        snapshot=snapshot,
        receipt=receipt,
    )


def build_risk_gate_bundle_from_proposal_snapshot(
    proposal_snapshot: ProposalSnapshot | dict[str, Any],
    *,
    context: RiskGateContext | dict[str, Any] | None = None,
    allocation_summary: RiskfolioAllocationSummary | dict[str, Any] | None = None,
    llm_enabled: bool = False,
    hermes_root: str | Path = "/root/projects/hermes-agent",
) -> RiskGateBundle:
    snapshot = (
        proposal_snapshot
        if isinstance(proposal_snapshot, ProposalSnapshot)
        else ProposalSnapshot.model_validate(proposal_snapshot)
    )
    risk_context = (
        context
        if isinstance(context, RiskGateContext)
        else RiskGateContext.model_validate(context or {})
    )
    allocation = normalize_allocation_summary(allocation_summary)
    representative_context = representative_risk_context(
        context=risk_context,
        proposal_snapshot=snapshot,
        allocation_summary=allocation,
    )
    source = RiskGateSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesRiskGateDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=str(hermes_root),
        config={
            "input_proposal_snapshot_id": snapshot.proposal_snapshot_id,
            "candidate_count": snapshot.candidate_count,
            "mandate_id": representative_context.mandate_id,
            "portfolio_risk_backend": allocation.backend if allocation else None,
        },
    )
    decisions = build_risk_gate_decisions(
        proposal_snapshot=snapshot,
        context=representative_context,
        allocation_summary=allocation,
    )
    return persist_risk_gate_bundle(
        source=source,
        input_proposal_snapshot=snapshot,
        context=representative_context,
        decisions=decisions,
    )
