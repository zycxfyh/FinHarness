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


class AgentWorkPlaybookBinding(BaseModel):
    """Playbook bound to a work loop — requirements validated."""

    model_config = ConfigDict(frozen=True)

    playbook_name: str
    version: str
    required_context_packs: list[str] = Field(default_factory=list)
    recommended_evaluators: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    bound: bool = False


def bind_playbook_to_work(playbook_name: str) -> AgentWorkPlaybookBinding:
    """Load a playbook and validate its requirements.

    Returns a binding that records whether all requirements are met.
    If playbook is missing or has unmet requirements, bound=False
    and findings are populated.
    """
    from finharness.evaluator_registry import evaluator_ids
    from finharness.playbook_loader import load_cognition_playbook

    pb = load_cognition_playbook(playbook_name)
    if pb is None:
        return AgentWorkPlaybookBinding(
            playbook_name=playbook_name,
            version="unknown",
            findings=[f"playbook '{playbook_name}' not found"],
            bound=False,
        )

    finding_msgs: list[str] = []
    bound = True
    registered_ids = set(evaluator_ids())

    for eid in pb.recommended_evaluators:
        if eid not in registered_ids:
            finding_msgs.append(
                f"recommended evaluator '{eid}' not registered"
            )
            bound = False

    return AgentWorkPlaybookBinding(
        playbook_name=playbook_name,
        version=pb.version,
        required_context_packs=pb.required_context_packs,
        recommended_evaluators=pb.recommended_evaluators,
        findings=finding_msgs,
        bound=bound,
    )


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


# ── bounded tool dispatch loop ────────────────────────────────────────


def run_bounded_tool_dispatch_loop(
    *,
    request: AgentWorkRequest,
    context_snapshot: AgentWorkContextSnapshot,
) -> tuple[list[dict[str, object]], str, list[str]]:
    """Run a bounded tool dispatch loop for a work request.

    Dispatches requested_tools in order, respecting max_tool_calls budget.
    Each dispatch passes through AgentRuntimeTraceSink for automatic
    trace recording. Returns (envelopes_as_dicts, stop_reason, data_gaps).

    Rules:
    - max max_tool_calls dispatches
    - Only profile_exposed + available tools
    - Only read / local_eval / append_only_review_write
    - Each result produces an AgentToolResultEnvelope
    - Trace sink writes AgentRunReceipt at completion
    """
    from pathlib import Path

    from finharness.agent_runtime_receipts import AgentRuntimeTraceSink
    from finharness.agent_tool_availability import capture_tool_universe_snapshot
    from finharness.agent_tool_result_envelope import build_tool_result_envelope

    receipt_root = Path(request.receipt_root)
    sink = AgentRuntimeTraceSink(
        goal=request.goal,
        profile_name=request.profile_name,
        receipt_root=receipt_root,
    )

    universe = capture_tool_universe_snapshot(request.profile_name)
    available_tools = set(universe.model_visible_tools)

    envelopes: list[dict[str, object]] = []
    data_gaps: list[str] = []

    tool_count = 0
    for tool_name in request.requested_tools:
        if tool_count >= request.max_tool_calls:
            break

        if tool_name not in available_tools:
            data_gaps.append(
                f"tool_unavailable: {tool_name} not available for "
                f"profile {request.profile_name!r}"
            )
            tool_count += 1
            continue

        result = sink.dispatch(
            profile_name=request.profile_name,
            tool_name=tool_name,
            arguments={},
        )

        env = build_tool_result_envelope(result)
        envelopes.append(env.model_dump())
        data_gaps.extend(env.data_gaps)
        tool_count += 1

    stop_reason = "completed"
    if tool_count >= request.max_tool_calls and tool_count == len(request.requested_tools):
        stop_reason = "completed"
    elif tool_count >= request.max_tool_calls:
        stop_reason = "max_tool_calls_reached"

    # Finalize trace sink -> AgentRunReceipt written
    from contextlib import suppress
    with suppress(ValueError):
        sink.finalize()

    return envelopes, stop_reason, data_gaps
