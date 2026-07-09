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
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

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


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"
