"""Agent Work Loop v0 — bounded, auditable agent work cycle.

Agentic-space dimension: All Spaces.
Operating surface: Track G — Agent Work Loop.

A work loop accepts an AgentWorkRequest with explicit budget and
produces an AgentWorkResult with full audit trail. It orchestrates
the existing surfaces (registry, universe, context, trace, evaluation,
workspace, search) into a single bounded execution unit.

Work loop is NOT: session, scheduler, execution, or multi-agent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    pass

NON_CLAIMS: tuple[str, ...] = (
    "Agent Work Loop produces review artifacts, not execution orders.",
    "Results require human review before any downstream action.",
    "Not investment advice.",
)

AgentWorkType = Literal[
    "research_review",
    "ips_drift_review",
    "proposal_review",
    "evidence_triage",
    "planning_review",
]

AgentWorkOutcome = Literal[
    "succeeded",
    "partial",
    "failed",
    "stopped",
]


class AgentWorkRequest(BaseModel):
    """A bounded work request for the agent work loop.

    Carries explicit budget (max_tool_calls, max_steps) and a
    deterministic tool execution plan (requested_tools in order).
    No LLM planning — tool selection is explicit.
    """

    model_config = ConfigDict(frozen=True)

    work_id: str = Field(default_factory=lambda: _new_id("awr"))
    goal: str
    profile_name: str
    objective: str
    work_type: AgentWorkType
    playbook_name: str | None = None
    requested_tools: list[str] = Field(default_factory=list)
    context_pack_names: list[str] = Field(default_factory=list)
    max_tool_calls: int = 5
    max_steps: int = 8
    receipt_root: str
    execution_allowed: Literal[False] = False


class AgentWorkResult(BaseModel):
    """The output of one agent work loop execution.

    Links to all produced artifacts: trace receipt, evaluation report,
    authority transition, review workspace, and search index entry.
    """

    model_config = ConfigDict(frozen=True)

    work_id: str
    goal: str
    profile_name: str
    work_type: AgentWorkType
    outcome: AgentWorkOutcome
    stop_reason: str
    tool_result_refs: list[str] = Field(default_factory=list)
    agent_run_receipt_ref: str | None = None
    evaluation_report_ref: str | None = None
    authority_transition_ref: str | None = None
    review_workspace_ref: str | None = None
    search_index_ref: str | None = None
    data_gaps: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    execution_allowed: Literal[False] = False


class AgentWorkContextSnapshot(BaseModel):
    """Frozen context projection snapshot for a work loop.

    The work loop consumes only this snapshot — no dynamic context
    reads during execution. This mirrors Hermes memory's frozen
    prompt snapshot pattern.
    """

    model_config = ConfigDict(frozen=True)

    snapshot_id: str = Field(default_factory=lambda: _new_id("ctxsnap"))
    work_id: str
    profile_name: str
    context_projection_payload: dict[str, object] = Field(default_factory=dict)
    context_trust_by_ref: dict[str, object] = Field(default_factory=dict)
    context_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    created_at_utc: str = Field(default_factory=lambda: _now_utc())
    findings: list[dict[str, object]] = Field(default_factory=list)
    execution_allowed: Literal[False] = False


def freeze_work_context(
    *,
    work_id: str,
    profile_name: str,
    context_projection_payload: dict[str, object] | None = None,
) -> AgentWorkContextSnapshot:
    """Freeze a context projection into an immutable snapshot.

    Extracts context_trust_by_ref and findings from the projection
    payload so the work loop can consume them without runtime drift.
    """
    from finharness.agent_context_trust_map import extract_context_trust_map

    payload = context_projection_payload or {}
    extraction = extract_context_trust_map(payload)

    context_refs: list[str] = []
    source_refs: list[str] = []
    packs = payload.get("packs")
    if isinstance(packs, list):
        for pack in packs:
            if isinstance(pack, dict):
                cp_refs = pack.get("context_pack_refs")
                if isinstance(cp_refs, list):
                    context_refs.extend(str(r) for r in cp_refs)
                src_refs = pack.get("source_refs")
                if isinstance(src_refs, list):
                    source_refs.extend(str(r) for r in src_refs)

    trust_dict: dict[str, object] = {}
    for ref, trust in extraction.trust_by_ref.items():
        trust_dict[ref] = trust.model_dump()

    findings_list: list[dict[str, object]] = [
        f.model_dump() for f in extraction.findings
    ]

    return AgentWorkContextSnapshot(
        work_id=work_id,
        profile_name=profile_name,
        context_projection_payload=payload,
        context_trust_by_ref=trust_dict,
        context_refs=list(dict.fromkeys(context_refs)),
        source_refs=list(dict.fromkeys(source_refs)),
        findings=findings_list,
    )


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()
