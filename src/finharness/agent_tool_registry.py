"""AgentToolRegistry v0 — discoverable tool registration layer.

Agentic-space dimension: Action Space / Tool Surface.
Operating surface: Track A — Agent Tool Surface.

Registered != exposed != evidence-eligible != authority-eligible != execution-authorized.

This registry defines what tools exist and governs visibility/exposure rules.
It does NOT change dispatch behavior, tool availability, or the existing
AGENT_TOOL_ENTRIES dictionary in agent_tools.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.agent_capabilities import AgentCapability
from finharness.agent_tools import (
    AGENT_TOOL_ENTRIES,
    AgentToolSideEffect,
)
from finharness.agent_tools import (
    AgentToolEntry as _AgentToolEntry,
)

AgentToolOutputKind = Literal[
    "context",
    "evidence",
    "artifact",
    "message",
    "diagnostic",
]

AgentToolVisibility = Literal[
    "registered",
    "profile_exposed",
    "evidence_eligible",
    "authority_eligible",
    "execution_authorized",
]

NON_CLAIMS: tuple[str, ...] = (
    "AgentToolRegistry records tool metadata, not execution authority.",
    "Registered != exposed != evidence-eligible != execution-authorized.",
    "Not investment advice.",
)


class AgentToolRegistration(BaseModel):
    """Registry-level metadata for one agent tool.

    This is the discoverable registration entry — lighter than the full
    AgentToolEntry (which carries dispatch handlers and SDK adapters).
    """

    model_config = ConfigDict(frozen=True)

    name: str
    toolset: str
    description: str
    capability: str
    side_effect: AgentToolSideEffect
    output_kind: AgentToolOutputKind
    evidence_provider_ids: list[str] = Field(default_factory=list)
    profile_allowlist: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    check_fn_name: str | None = None
    execution_allowed: bool = False
    authority_transition: bool = False

    def visibility_chain(self) -> dict[str, bool]:
        """Return the 5-tier visibility chain for this tool."""
        return {
            "registered": True,
            "profile_exposed": len(self.profile_allowlist) > 0,
            "evidence_eligible": len(self.evidence_provider_ids) > 0,
            "authority_eligible": False,
            "execution_authorized": False,
        }

    def non_claims(self) -> list[str]:
        return list(NON_CLAIMS)


# ── output_kind classification ────────────────────────────────────────

_OUTPUT_KIND_MAP: dict[AgentToolSideEffect, AgentToolOutputKind] = {
    "read": "context",
    "local_eval": "evidence",
    "append_only_review_write": "artifact",
}


def _classify_output_kind(
    side_effect: AgentToolSideEffect,
    capability: AgentCapability,
) -> AgentToolOutputKind:
    """Classify a tool's output_kind from its side_effect and capability."""
    return _OUTPUT_KIND_MAP.get(side_effect, "diagnostic")


# ── profile allowlist derivation ──────────────────────────────────────


_PROFILE_NAMES = ("default", "review-draft", "review-note", "scaffold-candidate")


def _profile_allowlist_for_entry(entry: _AgentToolEntry) -> list[str]:
    """Derive profile allowlist from existing tool entry.

    Reads from current agent profiles to determine which profiles permit
    this tool. This is a best-effort projection — not a policy engine.
    """
    from finharness.agent_capabilities import profile_allows_capability

    profiles: list[str] = []
    for profile_name in _PROFILE_NAMES:
        try:
            if profile_allows_capability(profile_name, entry.capability):
                profiles.append(profile_name)
        except ValueError:
            continue
    return profiles


# ── registry population ───────────────────────────────────────────────


def _from_agent_tool_entry(entry: _AgentToolEntry) -> AgentToolRegistration:
    """Convert an existing AgentToolEntry to an AgentToolRegistration."""
    return AgentToolRegistration(
        name=entry.name,
        toolset=entry.toolset,
        description=entry.description,
        capability=entry.capability.value,
        side_effect=entry.side_effect,
        output_kind=_classify_output_kind(entry.side_effect, entry.capability),
        evidence_provider_ids=list(entry.evidence_provider_ids),
        profile_allowlist=_profile_allowlist_for_entry(entry),
        requires_human_review=entry.requires_human_review,
        check_fn_name=_check_fn_name_for_entry(entry),
        execution_allowed=False,
        authority_transition=False,
    )


def _check_fn_name_for_entry(entry: _AgentToolEntry) -> str | None:
    """Extract a human-readable check function name from a tool entry."""
    fn = entry.check_fn
    name = getattr(fn, "__name__", None)
    if name and name != "<lambda>":
        return name
    return None


def build_registry() -> list[AgentToolRegistration]:
    """Build the complete tool registry from existing AGENT_TOOL_ENTRIES.

    This is a deterministic projection — it reads the live tool dictionary
    and produces registration entries. No state mutation.
    """
    registrations: list[AgentToolRegistration] = []
    for name in sorted(AGENT_TOOL_ENTRIES):
        entry = AGENT_TOOL_ENTRIES[name]
        try:
            reg = _from_agent_tool_entry(entry)
            registrations.append(reg)
        except (ValueError, TypeError):
            # Skip tools that fail to register — registry is best-effort metadata
            continue
    return registrations


# ── registry queries ──────────────────────────────────────────────────


def registered_tools() -> list[str]:
    """Return all registered tool names (alphabetical)."""
    return sorted(AGENT_TOOL_ENTRIES)


def tools_by_toolset(toolset: str) -> list[AgentToolRegistration]:
    """Return registrations for a given toolset."""
    return [r for r in build_registry() if r.toolset == toolset]


def tools_by_output_kind(kind: AgentToolOutputKind) -> list[AgentToolRegistration]:
    """Return registrations for a given output_kind."""
    return [r for r in build_registry() if r.output_kind == kind]


def tools_exposed_to_profile(profile_name: str) -> list[AgentToolRegistration]:
    """Return registrations for tools exposed to a given profile."""
    return [r for r in build_registry() if profile_name in r.profile_allowlist]


def registry_summary() -> dict[str, object]:
    """Return a summary of the full registry."""
    all_tools = build_registry()
    toolsets: list[str] = sorted({r.toolset for r in all_tools})
    output_kinds: list[AgentToolOutputKind] = sorted({r.output_kind for r in all_tools})
    return {
        "total_registered": len(all_tools),
        "toolsets": toolsets,
        "output_kinds": output_kinds,
        "by_toolset": {ts: len(tools_by_toolset(ts)) for ts in toolsets},
        "by_output_kind": {
            ok: len(tools_by_output_kind(ok))
            for ok in output_kinds
        },
        "evidence_eligible_count": sum(
            1 for r in all_tools if r.visibility_chain()["evidence_eligible"]
        ),
        "execution_authorized_count": 0,
        "non_claims": list(NON_CLAIMS),
    }
