"""OpenAI Agents SDK tools for the FinHarness lab."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from agents import Agent, FunctionTool, Tool, function_tool
from sqlalchemy.engine import Engine
from sqlmodel import Session

from finharness.agent_capabilities import (
    AgentCapability,
    get_agent_profile,
    profile_allows_capability,
    tool_names_for_profile,
)
from finharness.agent_context import (
    AgentContextPack,
    build_capital_summary_context,
    build_current_ips_context,
    build_ips_check_context,
    build_open_proposals_context,
    build_proposal_timeline_context,
    unavailable_context_pack,
)
from finharness.agent_context_projection import build_capital_context_projection_payload
from finharness.agent_evidence import (
    local_eval_source_ref,
    market_data_source_ref,
    resolve_evidence_providers,
)
from finharness.config import load_settings
from finharness.data_entry import fetch_quote_snapshot, fetch_yfinance_history
from finharness.metrics import summarize
from finharness.risk_register import read_review_risk_register
from finharness.statecore.decision_scaffold import ALL_FIELDS, ensure_forcing, normalize
from finharness.statecore.models import Proposal
from finharness.statecore.proposals import (
    create_governed_proposal,
    create_governed_review_event,
)
from finharness.statecore.store import (
    StateCoreStoreError,
    open_state_core,
    state_core_db_path,
)

ROOT = Path(__file__).resolve().parents[2]
LATEST_RISK_NOTE = ROOT / "data" / "cache" / "latest_risk_note.txt"
DEFAULT_RISK_NOTE = """Not investment advice.

This educational risk note uses yfinance/Yahoo Finance history and not TradingView/TV data.
Historical metrics do not guarantee future returns.

Max drawdown and volatility can change when market regimes, liquidity, or data freshness change.
Transaction costs, slippage, taxes, and venue constraints must be reviewed before any paper
or live use.
"""
AGENT_PROPOSAL_DRAFT_NON_CLAIMS = (
    "Agent-created proposals are review drafts, not recommendations.",
    "Human review is required before any decision of record.",
    "Not execution authorization.",
    "Not investment advice.",
)
AGENT_REVIEW_NOTE_DRAFT_NON_CLAIMS = (
    "Agent-created review notes are draft review artifacts, not approvals.",
    "Review notes do not revise proposals, attest decisions, or close review tasks.",
    "Human review is required before any decision of record.",
    "Not execution authorization.",
    "Not investment advice.",
)
AGENT_SCAFFOLD_REVISION_APPLY_CANDIDATE_NON_CLAIMS = (
    "Agent-created scaffold revision apply candidates are review artifacts, not applied revisions.",
    "Apply candidates do not revise proposals, attest decisions, approve/reject "
    "proposals, or authorize execution.",
    "Candidate preflight, risk coverage, and rollback fields are Agent-supplied "
    "candidate payload unless a later system preflight recomputes them.",
    "Human confirmation is required before any scaffold revision is applied.",
    "Not execution authorization.",
    "Not investment advice.",
)
AGENT_DRAFT_BLOCKED_KIND_TOKENS = frozenset(
    {
        "execute",
        "execution",
        "order",
        "transfer",
        "trade",
        "broker",
        "action",
        "intent",
    }
)
AGENT_REVIEW_NOTE_KINDS = frozenset(
    {
        "evidence_check",
        "risk_check",
        "policy_check",
        "counterargument",
        "data_gap",
        "human_question",
        "process_warning",
    }
)
AGENT_REVIEW_NOTE_SEVERITIES = frozenset(
    {
        "info",
        "low",
        "medium",
        "high",
        "blocking",
    }
)
AGENT_REVIEW_NOTE_FORBIDDEN_EXTRA_FIELDS = frozenset(
    {
        "execution_allowed",
        "authority_transition",
        "approval_status",
        "approval",
        "decision",
        "approve",
        "approved",
        "rejection",
        "reject",
        "rejected",
        "attestation",
        "attestation_ref",
    }
)
AGENT_NAME = "Finance Research Harness Agent"
AGENT_TOOL_ENTRY_NON_CLAIMS = (
    "Agent tool entries describe runtime visibility; they do not grant authority.",
    "Tool availability is diagnostic metadata, not approval.",
    "Not execution authorization.",
    "Not investment advice.",
)
AGENT_BASE_INSTRUCTIONS = (
    "Use profile-selected tools to inspect bounded FinHarness context packs, fetch data, "
    "run backtests, evaluate risk notes, and create only the review objects exposed by "
    "the active profile. "
    "Capital OS context packs are for explanation and review only; they never "
    "authorize actions or execution. "
    "Always state that outputs are for education, not investment advice. "
    "Always disclose that the current default data source is yfinance/Yahoo Finance, "
    "not TradingView/TV, and that optional providers are evidence sources only."
)

AgentToolSideEffect = Literal["read", "local_eval", "append_only_review_write"]
AgentToolset = Literal[
    "market_data",
    "eval",
    "capital_context",
    "proposal_draft",
    "proposal_review",
]
AgentToolUnavailablePolicy = Literal["hide", "diagnostic_stub", "fail_closed"]
AgentToolHandler = Callable[[dict[str, Any]], dict[str, object]]


@dataclass(frozen=True)
class AgentToolAvailability:
    """Cheap runtime availability result for a declared Agent tool."""

    available: bool
    reason: str | None = None

    def model(self) -> dict[str, object]:
        return {
            "available": self.available,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AgentToolEntry:
    """Hermes-style metadata wrapper around an Agents SDK tool."""

    name: str
    tool: FunctionTool
    capability: AgentCapability
    toolset: AgentToolset
    description: str
    side_effect: AgentToolSideEffect
    check_fn: Callable[[], AgentToolAvailability]
    dispatch_handler: AgentToolHandler
    evidence_provider_ids: tuple[str, ...] = ()
    unavailable_policy: AgentToolUnavailablePolicy = "hide"
    max_result_chars: int = 12_000
    requires_human_review: bool = False
    execution_allowed: bool = False
    authority_transition: bool = False
    non_claims: tuple[str, ...] = AGENT_TOOL_ENTRY_NON_CLAIMS

    def __post_init__(self) -> None:
        if self.name != self.tool.name:
            raise ValueError(f"agent tool entry name mismatch: {self.name} != {self.tool.name}")
        if self.execution_allowed:
            raise ValueError("agent tool entries never grant execution authority")
        if self.authority_transition:
            raise ValueError("agent tool entries never grant authority transitions")
        resolve_evidence_providers(self.evidence_provider_ids)

    def metadata(self) -> dict[str, object]:
        availability = self.check_fn()
        return {
            "name": self.name,
            "capability": self.capability.value,
            "toolset": self.toolset,
            "description": self.description,
            "side_effect": self.side_effect,
            "availability": availability.model(),
            "evidence_provider_ids": list(self.evidence_provider_ids),
            "unavailable_policy": self.unavailable_policy,
            "max_result_chars": self.max_result_chars,
            "requires_human_review": self.requires_human_review,
            "execution_allowed": False,
            "authority_transition": False,
            "non_claims": list(self.non_claims),
        }


def _available() -> AgentToolAvailability:
    return AgentToolAvailability(True)


def _state_core_path_available() -> AgentToolAvailability:
    path = state_core_db_path(load_settings().state_core_db_path)
    if path.exists():
        return AgentToolAvailability(True)
    return AgentToolAvailability(False, f"state-core sqlite file missing: {path}")


def _promptfoo_available() -> AgentToolAvailability:
    if shutil.which("pnpm") is None:
        return AgentToolAvailability(False, "pnpm is not available on PATH")
    return AgentToolAvailability(True)


def _call_payload(handler: Callable[..., dict[str, object]]) -> AgentToolHandler:
    def call(arguments: dict[str, Any]) -> dict[str, object]:
        return handler(**arguments)

    return call


@function_tool
def get_quote_snapshot(symbol: str) -> dict[str, object]:
    """Get a quote snapshot through the default available data provider."""
    return get_quote_snapshot_payload(symbol=symbol)


def get_quote_snapshot_payload(symbol: str) -> dict[str, object]:
    """Build the quote snapshot payload behind the Agents SDK adapter."""
    quote = fetch_quote_snapshot(symbol)
    payload = quote.__dict__.copy()
    payload["source_refs"] = [
        market_data_source_ref(
            provider=quote.provider,
            dataset="quote",
            symbol=quote.symbol,
        )
    ]
    payload["non_claims"] = [
        "Quote snapshots are descriptive market data, not investment advice.",
        "Not execution authorization.",
    ]
    return payload


@function_tool
def get_historical_risk_metrics(symbol: str, start: str, end: str) -> dict[str, object]:
    """Fetch yfinance/Yahoo Finance history and compute core risk metrics."""
    return historical_risk_metrics_payload(symbol=symbol, start=start, end=end)


def historical_risk_metrics_payload(symbol: str, start: str, end: str) -> dict[str, object]:
    """Build the historical risk metrics payload behind the Agents SDK adapter."""
    history = fetch_yfinance_history(symbol, start, end)
    metrics = summarize(history["close"].astype(float).tolist())
    return {
        "symbol": symbol,
        "start": start,
        "end": end,
        "rows": len(history),
        "data_source": "yfinance/Yahoo Finance, not TradingView/TV",
        "metrics": metrics.__dict__,
        "source_refs": [
            market_data_source_ref(
                provider="yfinance",
                dataset="history",
                symbol=symbol,
                qualifier=f"start={start}&end={end}",
            )
        ],
        "non_claims": [
            "Historical metrics are descriptive and do not predict future returns.",
            "Not investment advice.",
            "Not execution authorization.",
        ],
    }


@function_tool
def evaluate_latest_risk_note() -> dict[str, object]:
    """Run promptfoo assertions against the latest generated risk note."""
    return evaluate_latest_risk_note_payload()


def evaluate_latest_risk_note_payload(timeout_seconds: float = 60.0) -> dict[str, object]:
    """Run promptfoo assertions with a bounded subprocess timeout."""
    if not LATEST_RISK_NOTE.exists():
        LATEST_RISK_NOTE.parent.mkdir(parents=True, exist_ok=True)
        LATEST_RISK_NOTE.write_text(DEFAULT_RISK_NOTE, encoding="utf-8")

    command = [
        "pnpm",
        "exec",
        "promptfoo",
        "eval",
        "-c",
        "evals/promptfoo/risk-note.yaml",
        "--no-cache",
    ]
    try:
        result = subprocess.run(  # noqa: S603 -- fixed local promptfoo command, shell disabled.
            command,
            cwd=ROOT,
            env={
                **dict(os.environ),
                "PROMPTFOO_DISABLE_TELEMETRY": "1",
                "PROMPTFOO_DISABLE_UPDATE": "1",
            },
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout_tail": str(exc.output or "")[-2000:],
            "stderr_tail": f"promptfoo timed out after {timeout_seconds} seconds",
            "source_refs": [
                local_eval_source_ref("evals/promptfoo/risk-note.yaml"),
                "cache://latest_risk_note",
            ],
            "data_gaps": [f"promptfoo timed out after {timeout_seconds} seconds"],
            "non_claims": [
                "Local eval evidence is diagnostic; it does not prove correctness.",
                "Not execution authorization.",
            ],
        }
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
        "source_refs": [
            local_eval_source_ref("evals/promptfoo/risk-note.yaml"),
            "cache://latest_risk_note",
        ],
        "non_claims": [
            "Local eval evidence is diagnostic; it does not prove correctness.",
            "Not execution authorization.",
        ],
    }


def _pack_payload(pack: AgentContextPack) -> dict[str, object]:
    return pack.model_dump(mode="json")


def _with_default_engine(
    name: str,
    builder: Callable[..., AgentContextPack],
    *args: object,
    **kwargs: object,
) -> dict[str, object]:
    try:
        engine = open_state_core()
    except StateCoreStoreError as exc:
        return _pack_payload(unavailable_context_pack(name, str(exc)))
    try:
        pack = builder(engine, *args, **kwargs)
        return _pack_payload(pack)
    finally:
        engine.dispose()


def capital_summary_context_payload(engine: Engine | None = None) -> dict[str, object]:
    if engine is not None:
        return _pack_payload(build_capital_summary_context(engine))
    return _with_default_engine("capital_summary", build_capital_summary_context)


def current_ips_context_payload(engine: Engine | None = None) -> dict[str, object]:
    if engine is not None:
        return _pack_payload(build_current_ips_context(engine))
    return _with_default_engine("current_ips", build_current_ips_context)


def ips_check_context_payload(engine: Engine | None = None) -> dict[str, object]:
    if engine is not None:
        return _pack_payload(build_ips_check_context(engine))
    return _with_default_engine("ips_check", build_ips_check_context)


def open_proposals_context_payload(
    *, limit: int = 10, engine: Engine | None = None
) -> dict[str, object]:
    if engine is not None:
        return _pack_payload(build_open_proposals_context(engine, limit=limit))
    return _with_default_engine("open_proposals", build_open_proposals_context, limit=limit)


def proposal_timeline_context_payload(
    proposal_id: str,
    *,
    limit: int = 20,
    engine: Engine | None = None,
) -> dict[str, object]:
    if engine is not None:
        return _pack_payload(
            build_proposal_timeline_context(engine, proposal_id=proposal_id, limit=limit)
        )
    return _with_default_engine(
        "proposal_timeline",
        build_proposal_timeline_context,
        proposal_id=proposal_id,
        limit=limit,
    )


def capital_context_projection_payload(
    *,
    profile_name: str = "default",
    open_proposals_limit: int = 10,
    engine: Engine | None = None,
) -> dict[str, object]:
    return build_capital_context_projection_payload(
        profile_name=profile_name,
        open_proposals_limit=open_proposals_limit,
        engine=engine,
    )


def draft_governed_proposal_from_context_payload(
    *,
    kind: str,
    claim: str,
    evidence: dict[str, Any],
    decision_scaffold: dict[str, Any],
    source_refs: list[str],
    reason: str,
    assumptions: dict[str, Any] | None = None,
    limitations: dict[str, Any] | None = None,
    context_pack_refs: list[str] | None = None,
    profile_name: str = "review-draft",
    engine: Engine | None = None,
    receipt_root: str | Path | None = None,
) -> dict[str, object]:
    """Create an append-only governed proposal draft through the Agent profile gate."""
    _validate_agent_proposal_draft(
        profile_name=profile_name,
        kind=kind,
        claim=claim,
        reason=reason,
        evidence=evidence,
        decision_scaffold=decision_scaffold,
        assumptions=assumptions or {},
        limitations=limitations or {},
        source_refs=source_refs,
    )
    normalized_scaffold = ensure_forcing(decision_scaffold)
    refs = _dedupe_refs([*source_refs, *(context_pack_refs or [])])
    revision_context = {
        "kind": "agent_proposal_draft",
        "profile": profile_name,
        "reason": reason.strip(),
        "context_pack_refs": list(context_pack_refs or []),
        "requires_human_review": True,
        "execution_allowed": False,
    }
    owned_engine = engine is None
    active_engine = engine or open_state_core()
    active_receipt_root = Path(receipt_root or load_settings().receipt_root)
    try:
        write = create_governed_proposal(
            kind=kind.strip(),
            claim=claim.strip(),
            evidence=evidence,
            assumptions=assumptions or {},
            limitations=limitations or {},
            non_claims=list(AGENT_PROPOSAL_DRAFT_NON_CLAIMS),
            source_refs=refs,
            decision_scaffold=normalized_scaffold,
            engine=active_engine,
            receipt_root=active_receipt_root,
            revision_context=revision_context,
        )
    finally:
        if owned_engine:
            active_engine.dispose()
    return {
        "proposal_id": write.proposal.proposal_id,
        "kind": write.proposal.kind,
        "receipt_ref": write.receipt_ref,
        "authority_level": write.proposal.authority_level,
        "requires_human_review": True,
        "execution_allowed": False,
        "non_claims": write.proposal.non_claims,
        "source_refs": write.proposal.source_refs,
        "receipt_refs": [write.receipt_ref],
        "context_pack_refs": list(context_pack_refs or []),
    }


def draft_agent_review_note_from_context_payload(
    *,
    proposal_id: str,
    review_kind: str,
    suggested_severity: str,
    summary: str,
    rationale: str,
    findings: list[str],
    risks: list[str],
    open_questions: list[str],
    evidence_refs: list[str],
    source_refs: list[str],
    context_pack_refs: list[str] | None = None,
    data_gaps: list[str] | None = None,
    profile_name: str = "review-note",
    engine: Engine | None = None,
    receipt_root: str | Path | None = None,
    **extra: Any,
) -> dict[str, object]:
    """Create an append-only AgentReviewNoteDraft for an existing proposal."""
    _validate_agent_review_note_draft(
        profile_name=profile_name,
        proposal_id=proposal_id,
        review_kind=review_kind,
        suggested_severity=suggested_severity,
        summary=summary,
        rationale=rationale,
        findings=findings,
        risks=risks,
        open_questions=open_questions,
        evidence_refs=evidence_refs,
        source_refs=source_refs,
        context_pack_refs=context_pack_refs or [],
        data_gaps=data_gaps or [],
        extra=extra,
    )
    note_id = _agent_review_note_id()
    refs = _dedupe_refs(
        [
            *source_refs,
            *evidence_refs,
            *(context_pack_refs or []),
        ]
    )
    review_note = {
        "schema": "finharness.agent_review_note_draft.v1",
        "review_note_id": note_id,
        "proposal_id": proposal_id.strip(),
        "profile_name": profile_name,
        "review_kind": review_kind.strip(),
        "suggested_severity": suggested_severity.strip(),
        "summary": summary.strip(),
        "rationale": rationale.strip(),
        "findings": _clean_strings(findings),
        "risks": _clean_strings(risks),
        "open_questions": _clean_strings(open_questions),
        "evidence_refs": _dedupe_refs(evidence_refs),
        "source_refs": _dedupe_refs(source_refs),
        "context_pack_refs": _dedupe_refs(context_pack_refs or []),
        "data_gaps": _dedupe_refs(data_gaps or []),
        "non_claims": list(AGENT_REVIEW_NOTE_DRAFT_NON_CLAIMS),
        "transition_rule": {
            "may_enter_proposal_timeline": True,
            "may_enter_decision_packet": True,
            "may_trigger_open_question": True,
            "may_trigger_evidence_gap": True,
            "may_revise_proposal": False,
            "may_attest": False,
            "may_approve": False,
            "may_reject": False,
            "may_execute": False,
        },
        "requires_human_review": True,
        "execution_allowed": False,
        "authority_transition": False,
    }
    owned_engine = engine is None
    active_engine = engine or open_state_core()
    active_receipt_root = Path(receipt_root or load_settings().receipt_root)
    try:
        write = create_governed_review_event(
            proposal_id=proposal_id.strip(),
            kind="agent_review_note",
            attester=f"agent:{profile_name}",
            reason=rationale.strip(),
            text=json.dumps(
                review_note,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            source_refs=refs,
            engine=active_engine,
            receipt_root=active_receipt_root,
        )
    finally:
        if owned_engine:
            active_engine.dispose()
    review_note["review_event_id"] = write.review_event.review_event_id
    review_note["receipt_ref"] = write.receipt_ref
    return {
        **review_note,
        "receipt_refs": [write.receipt_ref],
    }


def draft_agent_scaffold_revision_apply_candidate_from_context_payload(
    *,
    proposal_id: str,
    scaffold_patch: dict[str, Any],
    change_summary: str,
    rationale: str,
    basis_risk_ids: list[str],
    risk_coverage: dict[str, Any],
    preflight_result: dict[str, Any],
    rollback_info: dict[str, Any],
    human_confirmation_requirements: list[str],
    source_refs: list[str],
    receipt_refs: list[str] | None = None,
    context_pack_refs: list[str] | None = None,
    data_gaps: list[str] | None = None,
    profile_name: str = "scaffold-candidate",
    engine: Engine | None = None,
    receipt_root: str | Path | None = None,
    **extra: Any,
) -> dict[str, object]:
    """Create an append-only AgentScaffoldRevisionApplyCandidate for a proposal."""
    _validate_agent_scaffold_revision_apply_candidate_inputs(
        profile_name=profile_name,
        proposal_id=proposal_id,
        scaffold_patch=scaffold_patch,
        change_summary=change_summary,
        rationale=rationale,
        basis_risk_ids=basis_risk_ids,
        risk_coverage=risk_coverage,
        preflight_result=preflight_result,
        rollback_info=rollback_info,
        human_confirmation_requirements=human_confirmation_requirements,
        source_refs=source_refs,
        receipt_refs=receipt_refs or [],
        context_pack_refs=context_pack_refs or [],
        data_gaps=data_gaps or [],
        extra=extra,
    )
    owned_engine = engine is None
    active_engine = engine or open_state_core()
    active_receipt_root = Path(receipt_root or load_settings().receipt_root)
    try:
        with Session(active_engine) as session:
            proposal = session.get(Proposal, proposal_id.strip())
            if proposal is None:
                raise ValueError(
                    "agent scaffold revision apply candidate references unknown proposal"
                )
            previous_scaffold = normalize(proposal.decision_scaffold)

        patch = normalize(scaffold_patch)
        proposed_scaffold = ensure_forcing({**previous_scaffold, **patch})
        changed_fields = [
            field
            for field in ALL_FIELDS
            if previous_scaffold.get(field) != proposed_scaffold.get(field)
        ]
        if not changed_fields:
            raise ValueError(
                "agent scaffold revision apply candidate requires at least one changed field"
            )
        _validate_basis_risks(
            engine=active_engine,
            receipt_root=active_receipt_root,
            proposal_id=proposal_id.strip(),
            basis_risk_ids=basis_risk_ids,
        )
        candidate_id = _agent_scaffold_revision_apply_candidate_id()
        refs = _dedupe_refs(
            [
                *source_refs,
                *(receipt_refs or []),
                *(context_pack_refs or []),
                *basis_risk_ids,
            ]
        )
        receipt_refs_clean = _dedupe_refs(receipt_refs or [])
        candidate = {
            "schema": "finharness.agent_scaffold_revision_apply_candidate.v1",
            "candidate_id": candidate_id,
            "proposal_id": proposal_id.strip(),
            "profile_name": profile_name,
            "consequence_class": "C2",
            "apply_candidate": True,
            "basis_risk_ids": _dedupe_refs(basis_risk_ids),
            "scaffold_patch": patch,
            "proposed_scaffold": proposed_scaffold,
            "changed_fields": changed_fields,
            "change_summary": change_summary.strip(),
            "rationale": rationale.strip(),
            "risk_coverage": copy.deepcopy(risk_coverage),
            "risk_coverage_source": "agent_supplied_candidate_payload",
            "preflight_result": copy.deepcopy(preflight_result),
            "preflight_result_source": "agent_supplied_candidate_payload",
            "system_preflight_recomputed": False,
            "rollback_info": copy.deepcopy(rollback_info),
            "rollback_info_source": "agent_supplied_candidate_payload",
            "human_confirmation_requirements": _clean_strings(
                human_confirmation_requirements
            ),
            "source_refs": _dedupe_refs(source_refs),
            "receipt_refs": receipt_refs_clean,
            "context_pack_refs": _dedupe_refs(context_pack_refs or []),
            "data_gaps": _dedupe_refs(data_gaps or []),
            "non_claims": list(
                AGENT_SCAFFOLD_REVISION_APPLY_CANDIDATE_NON_CLAIMS
            ),
            "transition_rule": {
                "may_enter_proposal_timeline": True,
                "may_be_applied_by_human_confirmed_flow": True,
                "may_revise_proposal_without_human_confirmation": False,
                "may_attest": False,
                "may_approve": False,
                "may_reject": False,
                "may_execute": False,
            },
            "requires_human_review": True,
            "execution_allowed": False,
            "authority_transition": False,
        }
        write = create_governed_review_event(
            proposal_id=proposal_id.strip(),
            kind="agent_scaffold_revision_apply_candidate",
            attester=f"agent:{profile_name}",
            reason=rationale.strip(),
            text=json.dumps(
                candidate,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            source_refs=refs,
            engine=active_engine,
            receipt_root=active_receipt_root,
        )
    finally:
        if owned_engine:
            active_engine.dispose()
    candidate["review_event_id"] = write.review_event.review_event_id
    candidate["receipt_ref"] = write.receipt_ref
    candidate["receipt_refs"] = _dedupe_refs([*receipt_refs_clean, write.receipt_ref])
    return candidate


def _validate_agent_proposal_draft(
    *,
    profile_name: str,
    kind: str,
    claim: str,
    reason: str,
    evidence: dict[str, Any],
    decision_scaffold: dict[str, Any],
    assumptions: dict[str, Any],
    limitations: dict[str, Any],
    source_refs: list[str],
) -> None:
    if not profile_allows_capability(profile_name, AgentCapability.CAPITAL_PROPOSE):
        raise ValueError(f"agent profile {profile_name!r} does not allow capital-propose")
    if not claim.strip():
        raise ValueError("agent proposal draft requires a non-blank claim")
    if not reason.strip():
        raise ValueError("agent proposal draft requires a non-blank reason")
    if not _dedupe_refs(source_refs):
        raise ValueError("agent proposal draft requires at least one source ref")
    kind_text = kind.strip().lower()
    if not kind_text:
        raise ValueError("agent proposal draft requires a non-blank kind")
    if _proposal_kind_tokens(kind_text) & AGENT_DRAFT_BLOCKED_KIND_TOKENS:
        raise ValueError("agent proposal draft kind cannot request execution/order/transfer")
    for name, value in (
        ("evidence", evidence),
        ("decision_scaffold", decision_scaffold),
        ("assumptions", assumptions),
        ("limitations", limitations),
    ):
        if _contains_execution_allowed_true(value):
            raise ValueError(f"{name} cannot set execution_allowed=true")


def _validate_agent_review_note_draft(
    *,
    profile_name: str,
    proposal_id: str,
    review_kind: str,
    suggested_severity: str,
    summary: str,
    rationale: str,
    findings: list[str],
    risks: list[str],
    open_questions: list[str],
    evidence_refs: list[str],
    source_refs: list[str],
    context_pack_refs: list[str],
    data_gaps: list[str],
    extra: dict[str, Any],
) -> None:
    if not profile_allows_capability(profile_name, AgentCapability.CAPITAL_REVIEW_NOTE):
        raise ValueError(f"agent profile {profile_name!r} does not allow capital-review-note")
    if not proposal_id.strip():
        raise ValueError("agent review note requires a non-blank proposal_id")
    _validate_agent_review_note_choice(
        review_kind=review_kind,
        suggested_severity=suggested_severity,
    )
    if not summary.strip():
        raise ValueError("agent review note requires a non-blank summary")
    if not rationale.strip():
        raise ValueError("agent review note requires a non-blank rationale")
    if not _dedupe_refs(source_refs):
        raise ValueError("agent review note requires at least one source ref")
    _reject_agent_review_note_extra(extra)
    _validate_agent_review_note_lists(
        findings=findings,
        risks=risks,
        open_questions=open_questions,
        evidence_refs=evidence_refs,
        source_refs=source_refs,
        context_pack_refs=context_pack_refs,
        data_gaps=data_gaps,
    )
    for name, value in (
        ("findings", findings),
        ("risks", risks),
        ("open_questions", open_questions),
        ("evidence_refs", evidence_refs),
        ("source_refs", source_refs),
        ("context_pack_refs", context_pack_refs),
        ("data_gaps", data_gaps),
        ("extra", extra),
    ):
        marker = _contains_forbidden_authority_marker(value)
        if marker is not None:
            raise ValueError(
                f"{name} cannot carry authority/decision marker {marker!r}"
            )


def _validate_agent_scaffold_revision_apply_candidate_inputs(
    *,
    profile_name: str,
    proposal_id: str,
    scaffold_patch: dict[str, Any],
    change_summary: str,
    rationale: str,
    basis_risk_ids: list[str],
    risk_coverage: dict[str, Any],
    preflight_result: dict[str, Any],
    rollback_info: dict[str, Any],
    human_confirmation_requirements: list[str],
    source_refs: list[str],
    receipt_refs: list[str],
    context_pack_refs: list[str],
    data_gaps: list[str],
    extra: dict[str, Any],
) -> None:
    if not profile_allows_capability(
        profile_name, AgentCapability.CAPITAL_SCAFFOLD_REVISION
    ):
        raise ValueError(
            f"agent profile {profile_name!r} does not allow capital-scaffold-revision"
        )
    if not proposal_id.strip():
        raise ValueError(
            "agent scaffold revision apply candidate requires a non-blank proposal_id"
        )
    if not isinstance(scaffold_patch, dict):
        raise ValueError("agent scaffold revision apply candidate scaffold_patch must be an object")
    unknown_scaffold_fields = sorted(set(scaffold_patch) - set(ALL_FIELDS))
    if unknown_scaffold_fields:
        raise ValueError(
            "agent scaffold revision apply candidate scaffold_patch has unknown field(s): "
            + ", ".join(unknown_scaffold_fields)
        )
    if not normalize(scaffold_patch):
        raise ValueError(
            "agent scaffold revision apply candidate requires a non-empty scaffold_patch"
        )
    if not change_summary.strip():
        raise ValueError("agent scaffold revision apply candidate requires a change_summary")
    if not rationale.strip():
        raise ValueError("agent scaffold revision apply candidate requires a rationale")
    if not _dedupe_refs(basis_risk_ids):
        raise ValueError("agent scaffold revision apply candidate requires basis_risk_ids")
    if not _dedupe_refs(source_refs):
        raise ValueError("agent scaffold revision apply candidate requires at least one source ref")
    _validate_scaffold_candidate_shapes(
        basis_risk_ids=basis_risk_ids,
        risk_coverage=risk_coverage,
        preflight_result=preflight_result,
        rollback_info=rollback_info,
        human_confirmation_requirements=human_confirmation_requirements,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
        context_pack_refs=context_pack_refs,
        data_gaps=data_gaps,
    )
    _reject_agent_review_note_extra(extra, artifact_name="agent scaffold revision apply candidate")
    _reject_forbidden_authority_markers(
        artifact_values={
            "scaffold_patch": scaffold_patch,
            "risk_coverage": risk_coverage,
            "preflight_result": preflight_result,
            "rollback_info": rollback_info,
            "human_confirmation_requirements": human_confirmation_requirements,
            "source_refs": source_refs,
            "receipt_refs": receipt_refs,
            "context_pack_refs": context_pack_refs,
            "data_gaps": data_gaps,
            "extra": extra,
        }
    )


def _validate_scaffold_candidate_shapes(
    *,
    basis_risk_ids: list[str],
    risk_coverage: dict[str, Any],
    preflight_result: dict[str, Any],
    rollback_info: dict[str, Any],
    human_confirmation_requirements: list[str],
    source_refs: list[str],
    receipt_refs: list[str],
    context_pack_refs: list[str],
    data_gaps: list[str],
) -> None:
    for name, list_value in (
        ("basis_risk_ids", basis_risk_ids),
        ("human_confirmation_requirements", human_confirmation_requirements),
        ("source_refs", source_refs),
        ("receipt_refs", receipt_refs),
        ("context_pack_refs", context_pack_refs),
        ("data_gaps", data_gaps),
    ):
        if not isinstance(list_value, list):
            raise ValueError(f"agent scaffold revision apply candidate {name} must be a list")
    for name, dict_value in (
        ("risk_coverage", risk_coverage),
        ("preflight_result", preflight_result),
        ("rollback_info", rollback_info),
    ):
        if not isinstance(dict_value, dict):
            raise ValueError(f"agent scaffold revision apply candidate {name} must be an object")


def _reject_forbidden_authority_markers(
    *, artifact_values: dict[str, Any]
) -> None:
    for name, value in artifact_values.items():
        marker = _contains_forbidden_authority_marker(value)
        if marker is not None:
            raise ValueError(
                f"{name} cannot carry authority/decision marker {marker!r}"
            )


def _validate_basis_risks(
    *,
    engine: Engine,
    receipt_root: Path,
    proposal_id: str,
    basis_risk_ids: list[str],
) -> None:
    register = read_review_risk_register(
        engine,
        receipt_root=receipt_root,
        limit=500,
        include_closed=False,
    )
    active_risks = {item.risk_id: item for item in register.items}
    missing = [risk_id for risk_id in _dedupe_refs(basis_risk_ids) if risk_id not in active_risks]
    if missing:
        raise ValueError(
            "agent scaffold revision apply candidate references unknown active risk(s): "
            + ", ".join(missing)
        )
    unrelated = [
        risk_id
        for risk_id in _dedupe_refs(basis_risk_ids)
        if proposal_id not in active_risks[risk_id].related_proposal_ids
    ]
    if unrelated:
        raise ValueError(
            "agent scaffold revision apply candidate basis risk(s) are unrelated to proposal: "
            + ", ".join(unrelated)
        )


def _validate_agent_review_note_choice(
    *,
    review_kind: str,
    suggested_severity: str,
) -> None:
    if review_kind.strip() not in AGENT_REVIEW_NOTE_KINDS:
        raise ValueError(
            "agent review note kind must be one of "
            + ", ".join(sorted(AGENT_REVIEW_NOTE_KINDS))
        )
    if suggested_severity.strip() not in AGENT_REVIEW_NOTE_SEVERITIES:
        raise ValueError(
            "agent review note suggested_severity must be one of "
            + ", ".join(sorted(AGENT_REVIEW_NOTE_SEVERITIES))
        )


def _reject_agent_review_note_extra(
    extra: dict[str, Any], *, artifact_name: str = "agent review note"
) -> None:
    unknown = sorted(set(extra) - {"engine", "receipt_root"})
    if unknown:
        forbidden = sorted(set(unknown) & AGENT_REVIEW_NOTE_FORBIDDEN_EXTRA_FIELDS)
        if forbidden:
            raise ValueError(
                f"{artifact_name} cannot set authority/decision field(s): "
                + ", ".join(forbidden)
            )
        raise ValueError(
            f"{artifact_name} received unsupported field(s): " + ", ".join(unknown)
        )


def _validate_agent_review_note_lists(
    *,
    findings: list[str],
    risks: list[str],
    open_questions: list[str],
    evidence_refs: list[str],
    source_refs: list[str],
    context_pack_refs: list[str],
    data_gaps: list[str],
) -> None:
    for name, value in (
        ("findings", findings),
        ("risks", risks),
        ("open_questions", open_questions),
        ("evidence_refs", evidence_refs),
        ("source_refs", source_refs),
        ("context_pack_refs", context_pack_refs),
        ("data_gaps", data_gaps),
    ):
        if not isinstance(value, list):
            raise ValueError(f"agent review note {name} must be a list")


def _contains_execution_allowed_true(value: Any) -> bool:
    if isinstance(value, dict):
        return any(
            (key == "execution_allowed" and child is True)
            or _contains_execution_allowed_true(child)
            for key, child in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_execution_allowed_true(child) for child in value)
    return False


def _contains_forbidden_authority_marker(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in AGENT_REVIEW_NOTE_FORBIDDEN_EXTRA_FIELDS:
                return normalized
            if (marker := _contains_forbidden_authority_marker(child)) is not None:
                return marker
    if isinstance(value, (list, tuple)):
        for child in value:
            if (marker := _contains_forbidden_authority_marker(child)) is not None:
                return marker
    return None


def _proposal_kind_tokens(kind: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9]+", kind.lower()) if token}


def _agent_review_note_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"agent_review_note_{stamp}_{uuid4().hex[:8]}"


def _agent_scaffold_revision_apply_candidate_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"agent_scaffold_candidate_{stamp}_{uuid4().hex[:8]}"


def _clean_strings(values: list[str]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]


def _dedupe_refs(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


@function_tool
def get_capital_context_projection(
    open_proposals_limit: int = 10,
) -> dict[str, object]:
    """Read the profile-budgeted Capital OS office context projection."""
    return capital_context_projection_payload(
        open_proposals_limit=open_proposals_limit,
    )


@function_tool
def get_capital_summary_context() -> dict[str, object]:
    """Read the bounded Capital OS exposure context pack."""
    return capital_summary_context_payload()


@function_tool
def get_current_ips_context() -> dict[str, object]:
    """Read the active IPS context pack, if one exists."""
    return current_ips_context_payload()


@function_tool
def get_ips_check_context() -> dict[str, object]:
    """Read the IPS compliance context pack for current exposure."""
    return ips_check_context_payload()


@function_tool
def get_open_proposals_context(limit: int = 10) -> dict[str, object]:
    """Read open governed proposals awaiting human review."""
    return open_proposals_context_payload(limit=limit)


@function_tool
def get_proposal_timeline_context(proposal_id: str, limit: int = 20) -> dict[str, object]:
    """Read a governed proposal's bounded review timeline."""
    return proposal_timeline_context_payload(proposal_id=proposal_id, limit=limit)


# The Agents SDK cannot currently keep strict mode for flexible nested evidence/scaffold
# dicts. The fixed top-level schema is tested; runtime validators govern nested content.
@function_tool(strict_mode=False)
def draft_governed_proposal_from_context(
    kind: str,
    claim: str,
    evidence: dict[str, Any],
    decision_scaffold: dict[str, Any],
    source_refs: list[str],
    reason: str,
    assumptions: dict[str, Any] | None = None,
    limitations: dict[str, Any] | None = None,
    context_pack_refs: list[str] | None = None,
) -> dict[str, object]:
    """Create a receipt-backed governed proposal draft for human review."""
    return draft_governed_proposal_from_context_payload(
        kind=kind,
        claim=claim,
        evidence=evidence,
        decision_scaffold=decision_scaffold,
        source_refs=source_refs,
        reason=reason,
        assumptions=assumptions,
        limitations=limitations,
        context_pack_refs=context_pack_refs,
    )


# The review-note tool keeps a fixed top-level schema. Runtime injects profile_name;
# validators reject authority/decision fields supplied through non-SDK dispatch.
@function_tool
def draft_agent_review_note_from_context(
    proposal_id: str,
    review_kind: str,
    suggested_severity: str,
    summary: str,
    rationale: str,
    findings: list[str],
    risks: list[str],
    open_questions: list[str],
    evidence_refs: list[str],
    source_refs: list[str],
    context_pack_refs: list[str] | None = None,
    data_gaps: list[str] | None = None,
) -> dict[str, object]:
    """Create an append-only AgentReviewNoteDraft for an existing proposal."""
    return draft_agent_review_note_from_context_payload(
        proposal_id=proposal_id,
        review_kind=review_kind,
        suggested_severity=suggested_severity,
        summary=summary,
        rationale=rationale,
        findings=findings,
        risks=risks,
        open_questions=open_questions,
        evidence_refs=evidence_refs,
        source_refs=source_refs,
        context_pack_refs=context_pack_refs,
        data_gaps=data_gaps,
    )


# Flexible nested patch/preflight/rollback objects are governed by runtime validators.
# Runtime injects profile_name; the model only supplies content and provenance.
@function_tool(strict_mode=False)
def draft_agent_scaffold_revision_apply_candidate_from_context(
    proposal_id: str,
    scaffold_patch: dict[str, Any],
    change_summary: str,
    rationale: str,
    basis_risk_ids: list[str],
    risk_coverage: dict[str, Any],
    preflight_result: dict[str, Any],
    rollback_info: dict[str, Any],
    human_confirmation_requirements: list[str],
    source_refs: list[str],
    receipt_refs: list[str] | None = None,
    context_pack_refs: list[str] | None = None,
    data_gaps: list[str] | None = None,
) -> dict[str, object]:
    """Create an append-only AgentScaffoldRevisionApplyCandidate."""
    return draft_agent_scaffold_revision_apply_candidate_from_context_payload(
        proposal_id=proposal_id,
        scaffold_patch=scaffold_patch,
        change_summary=change_summary,
        rationale=rationale,
        basis_risk_ids=basis_risk_ids,
        risk_coverage=risk_coverage,
        preflight_result=preflight_result,
        rollback_info=rollback_info,
        human_confirmation_requirements=human_confirmation_requirements,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
        context_pack_refs=context_pack_refs,
        data_gaps=data_gaps,
    )


AGENT_TOOL_ENTRIES: dict[str, AgentToolEntry] = {
    entry.name: entry
    for entry in (
        AgentToolEntry(
            name=get_quote_snapshot.name,
            tool=get_quote_snapshot,
            capability=AgentCapability.CAPITAL_READ,
            toolset="market_data",
            description="Read one quote snapshot through the configured market-data adapter.",
            side_effect="read",
            check_fn=_available,
            dispatch_handler=_call_payload(get_quote_snapshot_payload),
            evidence_provider_ids=("market_data.yfinance",),
        ),
        AgentToolEntry(
            name=get_historical_risk_metrics.name,
            tool=get_historical_risk_metrics,
            capability=AgentCapability.CAPITAL_READ,
            toolset="market_data",
            description="Fetch historical prices and compute descriptive risk metrics.",
            side_effect="read",
            check_fn=_available,
            dispatch_handler=_call_payload(historical_risk_metrics_payload),
            evidence_provider_ids=("market_data.yfinance",),
        ),
        AgentToolEntry(
            name=evaluate_latest_risk_note.name,
            tool=evaluate_latest_risk_note,
            capability=AgentCapability.CAPITAL_EXPLAIN,
            toolset="eval",
            description="Run local promptfoo assertions against the latest generated risk note.",
            side_effect="local_eval",
            check_fn=_promptfoo_available,
            dispatch_handler=_call_payload(evaluate_latest_risk_note_payload),
            evidence_provider_ids=("local_eval.promptfoo",),
            unavailable_policy="hide",
        ),
        AgentToolEntry(
            name=get_capital_context_projection.name,
            tool=get_capital_context_projection,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read the profile-budgeted Capital OS office context projection.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(capital_context_projection_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
            max_result_chars=20_000,
        ),
        AgentToolEntry(
            name=get_capital_summary_context.name,
            tool=get_capital_summary_context,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read the bounded Capital OS exposure context pack.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(capital_summary_context_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
        ),
        AgentToolEntry(
            name=get_current_ips_context.name,
            tool=get_current_ips_context,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read the active IPS context pack when one exists.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(current_ips_context_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
        ),
        AgentToolEntry(
            name=get_ips_check_context.name,
            tool=get_ips_check_context,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read the IPS compliance context pack for current exposure.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(ips_check_context_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
        ),
        AgentToolEntry(
            name=get_open_proposals_context.name,
            tool=get_open_proposals_context,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read open governed proposals awaiting human review.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(open_proposals_context_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
        ),
        AgentToolEntry(
            name=get_proposal_timeline_context.name,
            tool=get_proposal_timeline_context,
            capability=AgentCapability.CAPITAL_READ,
            toolset="capital_context",
            description="Read a governed proposal's bounded review timeline.",
            side_effect="read",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(proposal_timeline_context_payload),
            evidence_provider_ids=("capital_context.state_core",),
            unavailable_policy="diagnostic_stub",
        ),
        AgentToolEntry(
            name=draft_governed_proposal_from_context.name,
            tool=draft_governed_proposal_from_context,
            capability=AgentCapability.CAPITAL_PROPOSE,
            toolset="proposal_draft",
            description="Create an append-only governed proposal draft for human review.",
            side_effect="append_only_review_write",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(draft_governed_proposal_from_context_payload),
            evidence_provider_ids=(
                "capital_context.state_core",
                "proposal_receipt.state_core",
            ),
            unavailable_policy="fail_closed",
            requires_human_review=True,
        ),
        AgentToolEntry(
            name=draft_agent_review_note_from_context.name,
            tool=draft_agent_review_note_from_context,
            capability=AgentCapability.CAPITAL_REVIEW_NOTE,
            toolset="proposal_review",
            description=(
                "Create an append-only AgentReviewNoteDraft on an existing proposal "
                "for human review."
            ),
            side_effect="append_only_review_write",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(draft_agent_review_note_from_context_payload),
            evidence_provider_ids=(
                "capital_context.state_core",
                "proposal_receipt.state_core",
            ),
            unavailable_policy="fail_closed",
            requires_human_review=True,
        ),
        AgentToolEntry(
            name=draft_agent_scaffold_revision_apply_candidate_from_context.name,
            tool=draft_agent_scaffold_revision_apply_candidate_from_context,
            capability=AgentCapability.CAPITAL_SCAFFOLD_REVISION,
            toolset="proposal_review",
            description=(
                "Create an append-only AgentScaffoldRevisionApplyCandidate for "
                "human-confirmed scaffold revision apply."
            ),
            side_effect="append_only_review_write",
            check_fn=_state_core_path_available,
            dispatch_handler=_call_payload(
                draft_agent_scaffold_revision_apply_candidate_from_context_payload
            ),
            evidence_provider_ids=(
                "capital_context.state_core",
                "proposal_receipt.state_core",
            ),
            unavailable_policy="fail_closed",
            requires_human_review=True,
            max_result_chars=20_000,
        ),
    )
}
AGENT_TOOL_REGISTRY: dict[str, FunctionTool] = {
    name: entry.tool for name, entry in AGENT_TOOL_ENTRIES.items()
}


def agent_tool_entries_for_profile(profile_name: str = "default") -> list[AgentToolEntry]:
    names = tool_names_for_profile(profile_name)
    missing = [name for name in names if name not in AGENT_TOOL_ENTRIES]
    if missing:
        raise ValueError(
            f"agent profile {profile_name!r} references unregistered tools: "
            f"{', '.join(missing)}"
        )
    return [AGENT_TOOL_ENTRIES[name] for name in names]


def agent_tool_metadata_for_profile(profile_name: str = "default") -> list[dict[str, object]]:
    return [entry.metadata() for entry in agent_tool_entries_for_profile(profile_name)]


def agent_tools_for_profile(profile_name: str = "default") -> list[Tool]:
    from finharness.agent_runtime import resolve_agent_tool_entries

    return [
        _runtime_bound_tool(profile_name=profile_name, entry=resolved.entry)
        for resolved in resolve_agent_tool_entries(profile_name)
        if resolved.model_visible
    ]


def _static_agent_tools_for_profile(profile_name: str = "default") -> list[Tool]:
    return [
        _runtime_bound_tool(profile_name=profile_name, entry=entry)
        for entry in agent_tool_entries_for_profile(profile_name)
    ]


def _runtime_bound_tool(*, profile_name: str, entry: AgentToolEntry) -> FunctionTool:
    async def invoke(_context: object, arguments_json: str) -> dict[str, object]:
        try:
            parsed = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as exc:
            return _sdk_schema_error(entry=entry, reason=str(exc))
        if not isinstance(parsed, dict):
            return _sdk_schema_error(
                entry=entry,
                reason="tool arguments must be a JSON object",
            )

        from finharness.agent_runtime import dispatch_agent_tool

        return dispatch_agent_tool(
            profile_name=profile_name,
            tool_name=entry.name,
            arguments=parsed,
        ).model()

    return FunctionTool(
        name=entry.tool.name,
        description=entry.tool.description,
        params_json_schema=copy.deepcopy(entry.tool.params_json_schema),
        on_invoke_tool=invoke,
        strict_json_schema=entry.tool.strict_json_schema,
        is_enabled=entry.tool.is_enabled,
        tool_input_guardrails=entry.tool.tool_input_guardrails,
        tool_output_guardrails=entry.tool.tool_output_guardrails,
        needs_approval=entry.tool.needs_approval,
        timeout_seconds=entry.tool.timeout_seconds,
        timeout_behavior=entry.tool.timeout_behavior,
        timeout_error_function=entry.tool.timeout_error_function,
        defer_loading=entry.tool.defer_loading,
    )


def _sdk_schema_error(*, entry: AgentToolEntry, reason: str) -> dict[str, object]:
    return {
        "ok": False,
        "tool_name": entry.name,
        "side_effect": entry.side_effect,
        "result": None,
        "evidence": None,
        "error": {
            "code": "SCHEMA_VALIDATION_FAILED",
            "message": "invalid tool arguments JSON",
            "recoverable": True,
            "reason": reason,
            "execution_allowed": False,
            "authority_transition": False,
        },
        "truncated": False,
        "original_result_chars": None,
        "execution_allowed": False,
        "authority_transition": False,
    }


def build_finance_research_agent(profile_name: str = "default") -> Agent:
    profile = get_agent_profile(profile_name)
    instructions = (
        f"{AGENT_BASE_INSTRUCTIONS} "
        f"Active capability profile: {profile.name}. {profile.description} "
        "Agent capability profiles select visible tools; they do not grant authority. "
        "Execution is not allowed."
    )
    return Agent(
        name=AGENT_NAME,
        instructions=instructions,
        tools=agent_tools_for_profile(profile.name),
    )


finance_research_agent = Agent(
    name=AGENT_NAME,
    instructions=(
        f"{AGENT_BASE_INSTRUCTIONS} "
        "Active capability profile: default. "
        "Agent capability profiles select visible tools; they do not grant authority. "
        "Execution is not allowed."
    ),
    tools=_static_agent_tools_for_profile("default"),
)


def tool_names(profile_name: str = "default") -> list[str]:
    return list(tool_names_for_profile(profile_name))


def describe_agent(profile_name: str = "default") -> str:
    from finharness.agent_runtime import agent_runtime_view

    profile = get_agent_profile(profile_name)
    agent = build_finance_research_agent(profile.name)
    runtime_view = agent_runtime_view(profile.name)
    return json.dumps(
        {
            "agent": agent.name,
            "profile": profile.model_dump(mode="json"),
            "tools": [tool.name for tool in agent.tools],
            "tool_entries": agent_tool_metadata_for_profile(profile.name),
            **runtime_view,
        },
        indent=2,
        sort_keys=True,
    )
