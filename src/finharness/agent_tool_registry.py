"""AgentToolRegistry v0.1 — runtime-authoritative tool registration layer.

Agentic-space dimension: Action Space / Tool Surface.
Operating surface: Track A — Agent Tool Surface.

Registered != exposed != evidence-eligible != authority-eligible != execution-authorized.

The registry is the authoritative metadata source for tool discovery.
It does NOT change dispatch behavior or the existing AGENT_TOOL_ENTRIES
dictionary in agent_tools.py — but it is the canonical query surface for
tool metadata, replacing the old pattern of projecting from AGENT_TOOL_ENTRIES
into parallel data structures.

Breaking change from v0 (PR #205):
  build_registry() no longer silently skips conversion failures.
  It returns AgentToolRegistry (not list) with findings for bad entries.
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


class AgentToolRegistryFinding(BaseModel):
    """A finding produced during registry construction.

    Findings capture conversion failures, missing fields, or inconsistent
    metadata. In strict mode, block-severity findings prevent the registry
    from being built; in non-strict mode they are recorded for diagnostics.
    """

    model_config = ConfigDict(frozen=True)

    tool_name: str
    severity: Literal["warn", "block"]
    code: str
    message: str


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


class AgentToolRegistry(BaseModel):
    """Authoritative tool registry — the canonical query surface.

    Replaces the old pattern of build_registry() returning a bare list.
    Queries now go through registry object methods, not free functions
    that re-build on every call.
    """

    model_config = ConfigDict(frozen=True)

    generation: int = 1
    registrations: dict[str, AgentToolRegistration] = Field(default_factory=dict)
    findings: list[AgentToolRegistryFinding] = Field(default_factory=list)

    @property
    def registered_tools(self) -> list[str]:
        """Return sorted list of successfully registered tool names."""
        return sorted(self.registrations)

    @property
    def total_count(self) -> int:
        return len(self.registrations)

    @property
    def invalid_count(self) -> int:
        return len(self.findings)

    def tools_by_toolset(self, toolset: str) -> list[AgentToolRegistration]:
        """Return registrations for a given toolset."""
        return [r for r in self.registrations.values() if r.toolset == toolset]

    def tools_by_output_kind(self, kind: AgentToolOutputKind) -> list[AgentToolRegistration]:
        """Return registrations for a given output_kind."""
        return [r for r in self.registrations.values() if r.output_kind == kind]

    def tools_exposed_to_profile(self, profile_name: str) -> list[AgentToolRegistration]:
        """Return registrations for tools exposed to a given profile."""
        return [r for r in self.registrations.values() if profile_name in r.profile_allowlist]

    def summary(self) -> dict[str, object]:
        """Return a summary of the full registry."""
        toolsets: list[str] = sorted({r.toolset for r in self.registrations.values()})
        output_kinds: list[AgentToolOutputKind] = sorted(
            {r.output_kind for r in self.registrations.values()}
        )
        return {
            "total_registered": self.total_count,
            "invalid_count": self.invalid_count,
            "toolsets": toolsets,
            "output_kinds": output_kinds,
            "by_toolset": {ts: len(self.tools_by_toolset(ts)) for ts in toolsets},
            "by_output_kind": {
                ok: len(self.tools_by_output_kind(ok)) for ok in output_kinds
            },
            "evidence_eligible_count": sum(
                1 for r in self.registrations.values() if r.visibility_chain()["evidence_eligible"]
            ),
            "execution_authorized_count": 0,
            "non_claims": list(NON_CLAIMS),
        }


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


def build_registry(*, strict: bool = True) -> AgentToolRegistry:
    """Build the complete tool registry from existing AGENT_TOOL_ENTRIES.

    This is a deterministic projection — it reads the live tool dictionary
    and produces registration entries. No state mutation.

    In strict mode (default), any entry that fails conversion raises
    ValueError. In non-strict mode, failures are recorded as findings
    and the remaining entries are registered.

    Returns an AgentToolRegistry object — the single authoritative
    metadata surface for tool discovery. Callers should NOT maintain
    parallel data structures; query the registry object instead.
    """
    registrations: dict[str, AgentToolRegistration] = {}
    findings: list[AgentToolRegistryFinding] = []

    for name in sorted(AGENT_TOOL_ENTRIES):
        entry = AGENT_TOOL_ENTRIES[name]
        try:
            reg = _from_agent_tool_entry(entry)
            registrations[name] = reg
        except (ValueError, TypeError) as exc:
            finding = AgentToolRegistryFinding(
                tool_name=name,
                severity="block",
                code="registry_conversion_failure",
                message=f"Failed to convert AGENT_TOOL_ENTRIES[{name!r}]: {exc}",
            )
            if strict:
                raise ValueError(
                    f"Cannot build strict registry: tool {name!r} failed conversion: {exc}"
                ) from exc
            findings.append(finding)

    return AgentToolRegistry(
        generation=1,
        registrations=registrations,
        findings=findings,
    )


# ── registry queries (thin wrappers for backward compat) ──────────────
# These are provided for callers that haven't migrated to the object API.
# Prefer registry.tools_by_toolset(...) over tools_by_toolset(...).


def registered_tools() -> list[str]:
    """Return all registered tool names (alphabetical).

    Deprecated: prefer registry.registered_tools.
    """
    return sorted(AGENT_TOOL_ENTRIES)


def tools_by_toolset(toolset: str) -> list[AgentToolRegistration]:
    """Return registrations for a given toolset.

    Deprecated: prefer registry.tools_by_toolset(toolset).
    """
    registry = build_registry(strict=True)
    return registry.tools_by_toolset(toolset)


def tools_by_output_kind(kind: AgentToolOutputKind) -> list[AgentToolRegistration]:
    """Return registrations for a given output_kind.

    Deprecated: prefer registry.tools_by_output_kind(kind).
    """
    registry = build_registry(strict=True)
    return registry.tools_by_output_kind(kind)


def tools_exposed_to_profile(profile_name: str) -> list[AgentToolRegistration]:
    """Return registrations for tools exposed to a given profile.

    Deprecated: prefer registry.tools_exposed_to_profile(profile_name).
    """
    registry = build_registry(strict=True)
    return registry.tools_exposed_to_profile(profile_name)


def registry_summary() -> dict[str, object]:
    """Return a summary of the full registry.

    Deprecated: prefer registry.summary().
    """
    return build_registry(strict=True).summary()
