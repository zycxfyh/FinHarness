"""AgentToolAvailabilitySnapshot — receipt/projection-only tool availability snapshot.

Agentic-space dimension: Action Space / Tool Surface.
Operating surface: Track A — Agent Tool Surface.

Produces deterministic snapshots of tool availability/exposure state for
a given profile. Receipt/projection-only — no StateCore table.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.agent_runtime import resolve_agent_tool_entries

NON_CLAIMS: tuple[str, ...] = (
    "Tool availability snapshots are diagnostic metadata, not execution authority.",
    "Available tools are not evidence-eligible by default.",
    "Not investment advice.",
)


class AgentToolAvailabilitySnapshot(BaseModel):
    """Receipt-only snapshot of one tool's availability for a given profile."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    profile_name: str
    tool_name: str
    toolset: str
    registered: bool
    exposed: bool
    available: bool
    unavailable_reason: str | None = None
    side_effect: str
    output_kind: str
    checked_at: str
    execution_allowed: bool = False
    authority_transition: bool = False


class AgentToolAvailabilitySnapshotSet(BaseModel):
    """A set of availability snapshots for one profile at one point in time."""

    model_config = ConfigDict(frozen=True)

    set_id: str
    profile_name: str
    checked_at: str
    snapshots: list[AgentToolAvailabilitySnapshot] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)
    execution_allowed: bool = False
    authority_transition: bool = False


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"


def capture_tool_availability_snapshots(
    profile_name: str = "default",
) -> AgentToolAvailabilitySnapshotSet:
    """Capture tool availability snapshots for a given profile.

    Reads the live runtime's resolve_agent_tool_entries() to determine
    which tools are registered, exposed to the profile, and available.

    Returns a frozen snapshot set with per-tool state. This is a
    deterministic projection — no mutation, no persistence.
    """
    checked_at = _now_utc()
    set_id = _new_id("avail")
    resolved = resolve_agent_tool_entries(profile_name)

    snapshots: list[AgentToolAvailabilitySnapshot] = []
    available_count = 0
    exposed_count = 0

    for item in resolved:
        entry = item.entry
        avail = item.availability
        snapshot = AgentToolAvailabilitySnapshot(
            snapshot_id=_new_id("avs"),
            profile_name=profile_name,
            tool_name=entry.name,
            toolset=entry.toolset,
            registered=True,
            exposed=item.model_visible,
            available=avail.available,
            unavailable_reason=avail.reason if not avail.available else None,
            side_effect=entry.side_effect,
            output_kind=_classify_output_kind(entry.side_effect),
            checked_at=checked_at,
        )
        snapshots.append(snapshot)
        if snapshot.available:
            available_count += 1
        if snapshot.exposed:
            exposed_count += 1

    return AgentToolAvailabilitySnapshotSet(
        set_id=set_id,
        profile_name=profile_name,
        checked_at=checked_at,
        snapshots=snapshots,
        summary={
            "total_tools": len(snapshots),
            "exposed_count": exposed_count,
            "hidden_count": len(snapshots) - exposed_count,
            "available_count": available_count,
            "unavailable_count": len(snapshots) - available_count,
            "execution_allowed": False,
        },
    )


def snapshot_for_tool(
    profile_name: str,
    tool_name: str,
) -> AgentToolAvailabilitySnapshot | None:
    """Get a single tool's availability snapshot, or None if not found."""
    snapset = capture_tool_availability_snapshots(profile_name)
    for s in snapset.snapshots:
        if s.tool_name == tool_name:
            return s
    return None


_OUTPUT_KIND_MAP: dict[str, str] = {
    "read": "context",
    "local_eval": "evidence",
    "append_only_review_write": "artifact",
}


def _classify_output_kind(side_effect: str) -> str:
    return _OUTPUT_KIND_MAP.get(side_effect, "diagnostic")
