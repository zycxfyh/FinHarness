"""Eighth-layer independent risk gate governance.

Risk Gate consumes structured proposal candidates and produces permission-aware
decisions. It is not an execution layer, not an order router, and not final
sizing approval.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.market_data import ROOT, display_path, sha256_text
from finharness.proposal import ProposalCandidate, ProposalSnapshot

RISK_GATE_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "risk-gates"
RISK_GATE_RECEIPT_ROOT = ROOT / "data" / "receipts" / "risk-gates"

RiskGateDecisionValue = Literal[
    "approved_for_paper_review",
    "blocked",
    "needs_more_evidence",
    "needs_human_review",
    "rejected",
]

RiskGateCheckStatus = Literal["passed", "failed", "warning", "not_applicable"]

BLOCKED_RISK_GATE_LANGUAGE = [
    r"\bbuy\b(?!-side)",
    r"\bsell\b(?!-side)",
    r"\bhold\b",
    r"\bshort\b(?!-term|-run|-dated|-horizon)",
    r"\blong\b(?!-term|-run|-dated|-horizon)",
    r"\btarget price\b",
    r"\bprice target\b",
    r"\bplace order\b",
    r"\border\b",
    r"\bexecute\b",
    r"\blive execution\b",
    r"\bquantity\b",
    r"\bleverage\b",
    r"\bstop loss\b",
    r"\btake profit\b",
    "买入",
    "卖出",
    "持有",
    "做多",
    "做空",
    "目标价",
    "下单",
    "执行",
    "杠杆",
]


class RiskGateSourceSpec(BaseModel):
    """Source/config layer for risk-gate decisions."""

    model_config = ConfigDict(frozen=True)

    provider: str = "FinHarness deterministic risk gate"
    method: str = "rule_guided_risk_gate_mvp"
    input_layer: str = "proposal"
    template_version: str = "finharness.risk_gate.template.v1"
    llm_provider: str | None = None
    llm_interface: str | None = None
    llm_enabled: bool = False
    hermes_root: str | None = "/root/projects/hermes-agent"
    config: dict[str, Any] = Field(default_factory=dict)


class RiskGateContext(BaseModel):
    """Deterministic MVP context for risk checks."""

    model_config = ConfigDict(frozen=True)

    mandate_id: str = "paper_research_mandate_v1"
    mandate_text: str = "Paper research review only; no live execution."
    allowed_symbols: list[str] = Field(
        default_factory=lambda: [
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "NVDA",
            "META",
            "TSLA",
            "SPY",
            "QQQ",
        ]
    )
    allowed_action_types: list[str] = Field(
        default_factory=lambda: [
            "watch_only",
            "research_more",
            "paper_trade_candidate",
            "avoid_or_reject",
        ]
    )
    requested_execution_mode: Literal["none", "paper", "live"] = "paper"
    live_execution_allowed: bool = False
    # Fail-closed: attestation is an action a human takes, never a default.
    human_review_attested: bool = False
    max_paper_notional: float = 1000.0
    requested_notional: float = 100.0
    max_symbol_concentration_pct: float = 0.10
    requested_symbol_concentration_pct: float = 0.02
    liquidity_evidence_present: bool = True
    drawdown_pct: float = 0.0
    hard_stop_drawdown_pct: float = -3.0
    consecutive_losses: int = 0
    hard_stop_consecutive_losses: int = 3
    behavior_reset_required: bool = False
    scenario_review_present: bool = True


class RiskGateCheck(BaseModel):
    """One auditable risk-gate check."""

    model_config = ConfigDict(frozen=True)

    check_id: str
    proposal_id: str
    check_type: str
    status: RiskGateCheckStatus
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    blocked_language_hits: list[str] = Field(default_factory=list)
    blocking: bool = False
    created_at_utc: str


class RiskGateDecision(BaseModel):
    """Decision for one ProposalCandidate."""

    model_config = ConfigDict(frozen=True)

    decision_id: str
    proposal_id: str
    symbol: str
    action_type: str
    decision: RiskGateDecisionValue
    checks: list[RiskGateCheck]
    blocking_reasons: list[str]
    required_remediations: list[str]
    paper_review_allowed: bool
    live_execution_allowed: bool = False
    execution_intent: str = "no execution; execution layer is separate"
    sizing_intent: str = "no final sizing; risk gate decision only"
    human_review_required: bool = True
    created_at_utc: str


class RiskGateQuality(BaseModel):
    """Quality gates for risk-gate output."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    candidate_count: int
    decision_count: int
    proposal_snapshot_linked: bool
    proposal_quality_ok: bool
    decision_count_matches_candidate_count: bool
    all_decisions_have_checks: bool
    hard_blocks_enforced: bool
    mandate_present: bool
    permission_boundary_present: bool
    human_review_required: bool
    no_order_language: bool
    no_live_execution_authority: bool
    no_final_sizing: bool
    lineage_complete: bool
    receipt_written: bool
    missing_required_fields: dict[str, list[str]] = Field(default_factory=dict)
    blocked_language_hits: dict[str, list[str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class RiskGateLineage(BaseModel):
    """Lineage from ProposalSnapshot into risk-gate output."""

    model_config = ConfigDict(frozen=True)

    source: RiskGateSourceSpec
    input_proposal_snapshot_id: str
    input_proposal_receipt_ref: str
    proposal_ids: list[str]
    proposal_transform_version: str
    method: str
    model_provider: str | None = None
    prompt_template_version: str | None = None
    computed_at_utc: str
    transform_version: str = "finharness.risk_gate.v1"
    output_hash: str
    output_ref: str


class RiskGateSnapshot(BaseModel):
    """Stable eighth-layer risk-gate evidence."""

    model_config = ConfigDict(frozen=True)

    risk_gate_snapshot_id: str
    as_of_utc: str
    input_proposal_snapshot_id: str
    universe: list[str]
    candidate_count: int
    decision_count: int
    context: RiskGateContext
    decisions: list[RiskGateDecision]
    quality: RiskGateQuality
    lineage: RiskGateLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    execution_handoff: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class RiskGateReceipt(BaseModel):
    """Durable evidence root for eighth-layer risk-gate processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "risk_gate_processing"
    stage_flow: dict[str, str]
    snapshot: RiskGateSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class RiskGateBundle(BaseModel):
    """Compact handoff for scripts and graph nodes."""

    model_config = ConfigDict(frozen=True)

    source: RiskGateSourceSpec
    input_proposal_snapshot: ProposalSnapshot
    context: RiskGateContext
    decisions: list[RiskGateDecision]
    quality: RiskGateQuality
    lineage: RiskGateLineage
    snapshot: RiskGateSnapshot
    receipt: RiskGateReceipt


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def find_blocked_language(value: str) -> list[str]:
    lower = value.lower()
    hits: list[str] = []
    for pattern in BLOCKED_RISK_GATE_LANGUAGE:
        if re.search(pattern, lower):
            hits.append(pattern)
    return hits


def decision_text_for_guard(decision: RiskGateDecision) -> str:
    return "\n".join(
        [
            decision.execution_intent,
            decision.sizing_intent,
            *decision.blocking_reasons,
            *decision.required_remediations,
        ]
    )


def check(
    *,
    proposal_id: str,
    check_type: str,
    passed: bool,
    reason: str,
    evidence_refs: list[str] | None = None,
    blocked_language_hits: list[str] | None = None,
    blocking: bool = True,
) -> RiskGateCheck:
    return RiskGateCheck(
        check_id=f"rgchk_{uuid4().hex[:12]}",
        proposal_id=proposal_id,
        check_type=check_type,
        status="passed" if passed else "failed",
        reason=reason,
        evidence_refs=evidence_refs or [],
        blocked_language_hits=blocked_language_hits or [],
        blocking=blocking and not passed,
        created_at_utc=now_utc(),
    )


def candidate_checks(
    *,
    proposal_snapshot: ProposalSnapshot,
    candidate: ProposalCandidate,
    context: RiskGateContext,
) -> list[RiskGateCheck]:
    refs = [proposal_snapshot.payload_ref, proposal_snapshot.receipt_ref]
    candidate_language_hits = find_blocked_language(candidate.rationale)
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
            evidence_refs=[context.mandate_id],
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
        "max_notional_check",
        "concentration_check",
        "drawdown_state_check",
        "behavior_reset_check",
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
) -> RiskGateDecision:
    checks = candidate_checks(
        proposal_snapshot=proposal_snapshot,
        candidate=candidate,
        context=context,
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
        paper_review_allowed=paper_review_allowed,
        live_execution_allowed=False,
        human_review_required=True,
        created_at_utc=now_utc(),
    )


def build_risk_gate_decisions(
    *,
    proposal_snapshot: ProposalSnapshot,
    context: RiskGateContext,
) -> list[RiskGateDecision]:
    return [
        build_risk_gate_decision(
            proposal_snapshot=proposal_snapshot,
            candidate=candidate,
            context=context,
        )
        for candidate in proposal_snapshot.candidates
    ]


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
    output_ref = RISK_GATE_NORMALIZED_ROOT / f"{snapshot_id}.json"
    receipt_ref = RISK_GATE_RECEIPT_ROOT / f"{receipt_id}.json"
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
    source = RiskGateSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesRiskGateDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=str(hermes_root),
        config={
            "input_proposal_snapshot_id": snapshot.proposal_snapshot_id,
            "candidate_count": snapshot.candidate_count,
            "mandate_id": risk_context.mandate_id,
        },
    )
    decisions = build_risk_gate_decisions(
        proposal_snapshot=snapshot,
        context=risk_context,
    )
    return persist_risk_gate_bundle(
        source=source,
        input_proposal_snapshot=snapshot,
        context=risk_context,
        decisions=decisions,
    )
