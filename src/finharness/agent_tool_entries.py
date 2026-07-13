"""Shared Agent tool metadata, independent of runtime dispatch and tool construction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from agents import FunctionTool

from finharness.agent_capabilities import AgentCapability
from finharness.agent_evidence import resolve_evidence_providers

AGENT_TOOL_ENTRY_NON_CLAIMS = (
    "Agent tool entries describe runtime visibility; they do not grant authority.",
    "Tool availability is diagnostic metadata, not approval.",
    "Not execution authorization.",
    "Not investment advice.",
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
        return {"available": self.available, "reason": self.reason}


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


# Populated in place by agent_tools so runtime modules can share one registry
# without importing tool construction and creating a dependency cycle.
AGENT_TOOL_ENTRIES: dict[str, AgentToolEntry] = {}
