"""Seventh-layer structured proposal governance.

Proposal turns validation evidence into structured action candidates for risk
review. A proposal is not permission, not sizing approval, and not execution.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.market_data import ROOT, display_path, sha256_text
from finharness.validation import ValidationCheckResult, ValidationSnapshot

PROPOSAL_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "proposals"
PROPOSAL_RECEIPT_ROOT = ROOT / "data" / "receipts" / "proposals"
STRUCTURAL_READY_RESULTS = {"linked", "present", "well_formed"}

ActionType = Literal[
    "watch_only",
    "research_more",
    "paper_trade_candidate",
    "avoid_or_reject",
]

ProposalStatus = Literal[
    "draft_for_risk_review",
    "needs_more_research",
    "rejected_before_risk",
]

BLOCKED_PROPOSAL_LANGUAGE = [
    r"\bbuy\b(?!-side)",
    r"\bsell\b(?!-side)",
    r"\bhold\b",
    r"\bshort\b(?!-term|-run|-dated|-horizon)",
    r"\blong\b(?!-term|-run|-dated|-horizon)",
    r"\btarget price\b",
    r"\bprice target\b",
    r"\bplace order\b",
    r"\bapproved\b",
    r"\bauthorized\b",
    r"\bquantity\b",
    r"\bleverage\b",
    "买入",
    "卖出",
    "持有",
    "做多",
    "做空",
    "目标价",
    "下单",
    "批准",
    "授权",
    "杠杆",
]


class ProposalDraftProvider(Protocol):
    """Optional provider interface for future LLM proposal drafting."""

    provider_name: str

    def draft(self, validation_results: list[ValidationCheckResult]) -> dict[str, Any]:
        """Return optional draft proposal fields."""


class NullProposalDraftProvider:
    """Default provider: deterministic proposal, no LLM call."""

    provider_name = "none"

    def draft(self, validation_results: list[ValidationCheckResult]) -> dict[str, Any]:
        return {}


class HermesProposalDraftProvider:
    """Reserved adapter boundary for /root/projects/hermes-agent."""

    provider_name = "hermes-agent"

    def __init__(self, *, hermes_root: str | Path = "/root/projects/hermes-agent") -> None:
        self.hermes_root = Path(hermes_root)

    def draft(self, validation_results: list[ValidationCheckResult]) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "enabled": False,
            "hermes_root": str(self.hermes_root),
            "note": "LLM proposal interface reserved; deterministic template used in MVP.",
            "result_count": len(validation_results),
        }


class ProposalSourceSpec(BaseModel):
    """Source/config layer for proposal generation."""

    model_config = ConfigDict(frozen=True)

    provider: str = "FinHarness rule-guided proposal"
    method: str = "rule_guided_proposal_mvp"
    input_layer: str = "validation"
    template_version: str = "finharness.proposal.template.v1"
    llm_provider: str | None = None
    llm_interface: str | None = None
    llm_enabled: bool = False
    hermes_root: str | None = "/root/projects/hermes-agent"
    config: dict[str, Any] = Field(default_factory=dict)


class RiskGateRequest(BaseModel):
    """A request for independent risk-gate review."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    proposal_id: str
    required_checks: list[str]
    risk_budget_request: str
    sizing_intent: str
    execution_intent: str
    human_review_required: bool = True


class ProposalCandidate(BaseModel):
    """A structured action candidate for risk review only."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str
    source_validation_snapshot_id: str
    source_validation_result_ids: list[str]
    source_hypothesis_ids: list[str]
    symbol: str
    action_type: ActionType
    portfolio_role: str
    rationale: str
    evidence_summary: str
    validation_summary: str
    expected_benefit: str
    key_risks: list[str]
    invalidation_triggers: list[str]
    time_horizon: str
    benchmark_context: str
    scenario_notes: list[str]
    constraint_notes: list[str]
    risk_gate_request: RiskGateRequest
    alternatives_considered: list[str]
    do_nothing_case: str
    status: ProposalStatus
    draft_provider: str = "none"
    draft_ref: str | None = None
    created_at_utc: str


class ProposalQuality(BaseModel):
    """Quality gates for proposal output."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    candidate_count: int
    validation_snapshot_linked: bool
    validation_quality_ok: bool
    evidence_summary_present: bool
    validation_summary_present: bool
    portfolio_role_present: bool
    invalidation_triggers_present: bool
    risk_handoff_present: bool
    constraints_present: bool
    alternatives_considered: bool
    do_nothing_case_present: bool
    no_execution_authority: bool
    no_order_language: bool
    no_final_sizing: bool
    human_review_required: bool
    missing_required_fields: dict[str, list[str]] = Field(default_factory=dict)
    blocked_language_hits: dict[str, list[str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ProposalLineage(BaseModel):
    """Lineage from ValidationSnapshot into proposal output."""

    model_config = ConfigDict(frozen=True)

    source: ProposalSourceSpec
    input_validation_snapshot_id: str
    input_validation_receipt_ref: str
    validation_result_ids: list[str]
    hypothesis_ids: list[str]
    validation_transform_version: str
    method: str
    model_provider: str | None = None
    prompt_template_version: str | None = None
    computed_at_utc: str
    transform_version: str = "finharness.proposal.v1"
    output_hash: str
    output_ref: str


class ProposalSnapshot(BaseModel):
    """Stable seventh-layer proposal evidence."""

    model_config = ConfigDict(frozen=True)

    proposal_snapshot_id: str
    as_of_utc: str
    input_validation_snapshot_id: str
    universe: list[str]
    candidate_count: int
    candidates: list[ProposalCandidate]
    quality: ProposalQuality
    lineage: ProposalLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    risk_gate_handoff: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class ProposalReceipt(BaseModel):
    """Durable evidence root for seventh-layer proposal processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "proposal_processing"
    stage_flow: dict[str, str]
    snapshot: ProposalSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class ProposalBundle(BaseModel):
    """Compact handoff for scripts and graph nodes."""

    model_config = ConfigDict(frozen=True)

    source: ProposalSourceSpec
    input_validation_snapshot: ValidationSnapshot
    candidates: list[ProposalCandidate]
    quality: ProposalQuality
    lineage: ProposalLineage
    snapshot: ProposalSnapshot
    receipt: ProposalReceipt


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
    for pattern in BLOCKED_PROPOSAL_LANGUAGE:
        if re.search(pattern, lower):
            hits.append(pattern)
    return hits


def candidate_text_for_guard(candidate: ProposalCandidate) -> str:
    return "\n".join(
        [
            candidate.portfolio_role,
            candidate.rationale,
            candidate.evidence_summary,
            candidate.validation_summary,
            candidate.expected_benefit,
            candidate.time_horizon,
            candidate.benchmark_context,
            candidate.do_nothing_case,
            candidate.risk_gate_request.risk_budget_request,
            candidate.risk_gate_request.sizing_intent,
            candidate.risk_gate_request.execution_intent,
            *candidate.key_risks,
            *candidate.invalidation_triggers,
            *candidate.scenario_notes,
            *candidate.constraint_notes,
            *candidate.alternatives_considered,
        ]
    )


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


def persist_proposal_bundle(
    *,
    source: ProposalSourceSpec,
    input_validation_snapshot: ValidationSnapshot,
    candidates: list[ProposalCandidate],
) -> ProposalBundle:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    snapshot_id = f"props_{stamp}_{suffix}"
    receipt_id = f"receipt_{snapshot_id}"
    output_ref = PROPOSAL_NORMALIZED_ROOT / f"{snapshot_id}.json"
    receipt_ref = PROPOSAL_RECEIPT_ROOT / f"{receipt_id}.json"
    quality = build_proposal_quality(
        validation_snapshot=input_validation_snapshot,
        candidates=candidates,
    )
    output_payload = {
        "proposal_snapshot_id": snapshot_id,
        "input_validation_snapshot_id": input_validation_snapshot.validation_snapshot_id,
        "universe": input_validation_snapshot.universe,
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }
    output_hash = sha256_text(
        json.dumps(output_payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    lineage = ProposalLineage(
        source=source,
        input_validation_snapshot_id=input_validation_snapshot.validation_snapshot_id,
        input_validation_receipt_ref=input_validation_snapshot.receipt_ref,
        validation_result_ids=[
            result.check_id for result in input_validation_snapshot.results
        ],
        hypothesis_ids=input_validation_snapshot.lineage.hypothesis_ids,
        validation_transform_version=input_validation_snapshot.lineage.transform_version,
        method=source.method,
        model_provider=source.llm_provider if source.llm_enabled else None,
        prompt_template_version=source.template_version,
        computed_at_utc=now_utc(),
        output_hash=output_hash,
        output_ref=display_path(output_ref),
    )
    snapshot = ProposalSnapshot(
        proposal_snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        input_validation_snapshot_id=input_validation_snapshot.validation_snapshot_id,
        universe=input_validation_snapshot.universe,
        candidate_count=len(candidates),
        candidates=candidates,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(output_ref),
        receipt_ref=display_path(receipt_ref),
        execution_allowed=False,
        risk_gate_handoff=risk_gate_handoff(candidates),
        review_questions=snapshot_review_questions(candidates),
    )
    receipt = ProposalReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source_input": "ProposalSourceSpec + ValidationSnapshot",
            "candidate_selection": "ValidationResult groups by hypothesis",
            "proposal_formulation": "structured action candidate for risk review only",
            "invalidation": "candidate invalidation triggers required",
            "constraints": "risk gate checks and constraints required",
            "quality": "no execution authority, no orders, no final sizing",
            "lineage": "ValidationSnapshot refs, result ids, output hash/ref",
            "snapshot": "ProposalSnapshot",
            "receipt": "ProposalReceipt",
            "consumer_handoff": "risk gate review only",
        },
        snapshot=snapshot,
        status="ok" if quality.ok else "warning",
    )
    write_json(output_ref, output_payload)
    write_json(receipt_ref, receipt.model_dump(mode="json"))
    return ProposalBundle(
        source=source,
        input_validation_snapshot=input_validation_snapshot,
        candidates=candidates,
        quality=quality,
        lineage=lineage,
        snapshot=snapshot,
        receipt=receipt,
    )


def build_proposal_bundle_from_validation_snapshot(
    validation_snapshot: ValidationSnapshot | dict[str, Any],
    *,
    llm_enabled: bool = False,
    hermes_root: str | Path = "/root/projects/hermes-agent",
) -> ProposalBundle:
    snapshot = (
        validation_snapshot
        if isinstance(validation_snapshot, ValidationSnapshot)
        else ValidationSnapshot.model_validate(validation_snapshot)
    )
    source = ProposalSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesProposalDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=str(hermes_root),
        config={
            "input_validation_snapshot_id": snapshot.validation_snapshot_id,
            "result_count": snapshot.result_count,
        },
    )
    provider: ProposalDraftProvider
    if llm_enabled:
        provider = HermesProposalDraftProvider(hermes_root=hermes_root)
    else:
        provider = NullProposalDraftProvider()
    candidates = build_proposal_candidates(
        validation_snapshot=snapshot,
        draft_provider=provider,
    )
    return persist_proposal_bundle(
        source=source,
        input_validation_snapshot=snapshot,
        candidates=candidates,
    )
