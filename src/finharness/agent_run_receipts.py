"""AgentRunReceipt v0 — receipt-only trace of one agent run.

Agentic-space dimension: Trace Space.

AgentRunReceipt is not a business object. It is the first trace primitive
for Agent Cognition Runtime v0. It records what an agent run attempted,
what tools it called, what artifacts it produced, and how it ended.

Receipt-only, no StateCore table, no dispatch behavior change.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

AgentRunOutcome = Literal["succeeded", "partial", "blocked", "failed"]

NON_CLAIMS: tuple[str, ...] = (
    "AgentRunReceipt records agent activity, not business state.",
    "Not execution authorization.",
    "Not investment advice.",
)


class AgentToolCallSummary(BaseModel):
    """One tool invocation result inside an AgentRunReceipt."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    side_effect: str | None = None
    ok: bool
    evidence_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    error_code: str | None = None
    result_truncated: bool = False


class AgentRunReceipt(BaseModel):
    """Receipt-only trace of one agent run."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "finharness.agent_run_receipt.v1"
    receipt_id: str
    agent_run_id: str
    created_at_utc: str
    goal: str
    profile_name: str
    context_refs: list[str] = Field(default_factory=list)
    tool_calls: list[AgentToolCallSummary] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    outcome: AgentRunOutcome
    stop_reason: str
    non_claims: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    authority_transition: bool = False


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_agent_run_receipt(
    *,
    goal: str,
    profile_name: str,
    tool_calls: Sequence[AgentToolCallSummary],
    outcome: AgentRunOutcome,
    stop_reason: str,
    receipt_root: str | Path,
    context_refs: Sequence[str] = (),
    artifact_refs: Sequence[str] = (),
    evidence_refs: Sequence[str] = (),
    data_gaps: Sequence[str] = (),
) -> AgentRunReceipt:
    """Write a receipt-only AgentRunReceipt to the receipt root.

    This is an explicit, opt-in call — it does NOT auto-fire on every
    tool dispatch. It creates a JSON file under receipt_root/agent-runs/
    and returns the frozen receipt model.

    Raises ValueError if goal is empty.
    """
    if not goal.strip():
        raise ValueError("AgentRunReceipt requires a non-blank goal")

    receipt_id = _new_id("ar")
    agent_run_id = _new_id("agrun")

    receipt = AgentRunReceipt(
        receipt_id=receipt_id,
        agent_run_id=agent_run_id,
        created_at_utc=_now_utc(),
        goal=goal.strip(),
        profile_name=profile_name,
        context_refs=_dedupe_refs(context_refs),
        tool_calls=[_coerce_tool_call(tc) for tc in tool_calls],
        artifact_refs=_dedupe_refs(artifact_refs),
        evidence_refs=_dedupe_refs(evidence_refs),
        data_gaps=_dedupe_refs(data_gaps),
        outcome=outcome,
        stop_reason=stop_reason.strip(),
        non_claims=list(NON_CLAIMS),
    )

    root = Path(receipt_root)
    root.mkdir(parents=True, exist_ok=True)
    target_dir = root / "agent-runs"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{receipt_id}.json"
    file_path.write_text(
        receipt.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )

    return receipt


def _coerce_tool_call(tc: object) -> AgentToolCallSummary:
    """Accept either an AgentToolCallSummary or a dict with the same shape."""
    if isinstance(tc, AgentToolCallSummary):
        return tc
    if isinstance(tc, dict):
        return AgentToolCallSummary(**tc)
    raise TypeError(
        f"tool_call must be AgentToolCallSummary or dict, got {type(tc).__name__}"
    )


def _dedupe_refs(values: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
