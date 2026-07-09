"""AgentToolAvailabilitySnapshot — receipt/projection-only tool availability.

Agentic-space dimension: Action Space / Tool Surface.
Operating surface: Track A — Agent Tool Surface.

v0.1 (PR #207): Adds global tool universe snapshot (not just profile-resolved)
and cached availability checks with TTL and failure-grace window.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.agent_runtime import resolve_agent_tool_entries
from finharness.agent_tools import AGENT_TOOL_ENTRIES, AgentToolAvailability

NON_CLAIMS: tuple[str, ...] = (
    "Tool availability snapshots are diagnostic metadata, not execution authority.",
    "Available tools are not evidence-eligible by default.",
    "Not investment advice.",
)


# ── findings ─────────────────────────────────────────────────────────


class AgentToolAvailabilityFinding(BaseModel):
    """Diagnostic finding from availability computation."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    severity: Literal["warn", "block"]
    code: str
    message: str


# ── per-tool snapshot (existing, unchanged) ──────────────────────────


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


# ── global universe snapshot (new in v0.1) ───────────────────────────


class AgentToolUniverseSnapshot(BaseModel):
    """Global tool universe — all registered tools classified by visibility.

    Unlike the per-profile AgentToolAvailabilitySnapshotSet, this captures
    the FULL registered tool universe, distinguishing between tools that
    are:
      - registered but not profile-exposed (hidden from profile)
      - profile-exposed but unavailable (check_fn() returned false)
      - model-visible (passes check_fn() or diagnostic_stub)
    """

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    profile_name: str
    checked_at: str

    registered_tools: list[str] = Field(default_factory=list)
    profile_exposed_tools: list[str] = Field(default_factory=list)
    model_visible_tools: list[str] = Field(default_factory=list)
    hidden_tools: list[str] = Field(default_factory=list)
    unavailable_tools: list[str] = Field(default_factory=list)

    findings: list[AgentToolAvailabilityFinding] = Field(default_factory=list)

    execution_allowed: bool = False
    authority_transition: bool = False


# ── cached availability ──────────────────────────────────────────────

# Simple dict-based cache for deterministic check_fn() results.
# No thread locks — FinHarness is single-session local runtime.
_CACHE: dict[str, _CachedEntry] = {}


class _CachedEntry:
    """Cache entry with timestamp for TTL-based expiry."""

    __slots__ = ("available", "checked_at", "reason")

    def __init__(self, available: bool, reason: str | None, checked_at: float) -> None:
        self.available = available
        self.reason = reason
        self.checked_at = checked_at


def check_tool_availability_cached(
    tool_name: str,
    *,
    ttl_seconds: float = 30.0,
    failure_grace_seconds: float = 60.0,
) -> AgentToolAvailability:
    """Check tool availability with TTL-cache and failure grace.

    Caches check_fn() results for ttl_seconds. If a tool was recently
    available and a subsequent check fails within failure_grace_seconds,
    the tool is marked as degraded_available rather than immediately
    unavailable — this suppresses transient flake in external backends.

    Returns an AgentToolAvailability with one of:
      - available (cached or fresh check passed)
      - degraded_available (recently available, transient failure)
      - unavailable (never available or grace window expired)
    """
    entry = AGENT_TOOL_ENTRIES.get(tool_name)
    if entry is None:
        return AgentToolAvailability(
            available=False,
            reason=f"tool not registered: {tool_name}",
        )

    cache_key = tool_name
    now = time.monotonic()

    cached = _CACHE.get(cache_key)
    if cached is not None and (now - cached.checked_at) < ttl_seconds:
        # Within TTL — return cached result
        return AgentToolAvailability(
            available=cached.available,
            reason=cached.reason,
        )

    # Fresh check
    fresh = entry.check_fn()
    fresh_ts = now

    if fresh.available:
        _CACHE[cache_key] = _CachedEntry(
            available=True,
            reason=fresh.reason,
            checked_at=fresh_ts,
        )
        return AgentToolAvailability(
            available=True,
            reason=fresh.reason,
        )

    # Not available now — check failure grace
    if cached is not None and cached.available:
        grace_elapsed = now - cached.checked_at
        if grace_elapsed < failure_grace_seconds:
            # Transient failure — keep as degraded_available
            return AgentToolAvailability(
                available=True,
                reason=(
                    f"degraded_available: last success {grace_elapsed:.0f}s ago; "
                    f"current check: {fresh.reason}"
                ),
            )

    # Genuinely unavailable — update cache
    _CACHE[cache_key] = _CachedEntry(
        available=False,
        reason=fresh.reason,
        checked_at=fresh_ts,
    )
    return AgentToolAvailability(
        available=False,
        reason=fresh.reason,
    )


def clear_availability_cache() -> None:
    """Clear the availability cache (for tests)."""
    _CACHE.clear()


# ── helpers ──────────────────────────────────────────────────────────


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"


# ── profile snapshot (existing) ──────────────────────────────────────


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


# ── global universe snapshot (new) ───────────────────────────────────


def capture_tool_universe_snapshot(
    profile_name: str = "default",
) -> AgentToolUniverseSnapshot:
    """Capture the GLOBAL tool universe for a given profile.

    Unlike capture_tool_availability_snapshots() which only shows
    profile-resolved tools, this captures ALL registered tools and
    classifies them by visibility relative to the profile:

      - registered_tools: every tool in AGENT_TOOL_ENTRIES
      - profile_exposed_tools: tools in the profile's tool_names
      - model_visible_tools: profile-exposed AND (check_fn passes OR diagnostic_stub)
      - hidden_tools: profile-exposed but not model-visible (failed check, no diagnostic_stub)
      - unavailable_tools: profile-exposed but check_fn returned unavailable

    This is the authoritative answer to "what does the full tool
    universe look like for this profile?" — the per-profile snapshot
    only answers "what tools are currently resolved for this profile."
    """
    checked_at = _now_utc()
    snapshot_id = _new_id("univ")

    all_registered = sorted(AGENT_TOOL_ENTRIES)

    from finharness.agent_capabilities import tool_names_for_profile

    try:
        profile_tool_names = set(tool_names_for_profile(profile_name))
    except ValueError:
        profile_tool_names = set()

    resolved = resolve_agent_tool_entries(profile_name)
    model_visible = sorted(
        item.entry.name for item in resolved if item.model_visible
    )
    hidden = sorted(
        item.entry.name for item in resolved if not item.model_visible
    )
    unavailable = sorted(
        item.entry.name for item in resolved if not item.availability.available
    )

    # Tools registered but not exposed to this profile at all
    not_exposed = sorted(set(all_registered) - profile_tool_names)

    findings: list[AgentToolAvailabilityFinding] = []
    for tool_name in not_exposed:
        findings.append(
            AgentToolAvailabilityFinding(
                tool_name=tool_name,
                severity="warn",
                code="tool_not_profile_exposed",
                message=(
                    f"Tool {tool_name!r} is registered but not exposed "
                    f"to profile {profile_name!r}"
                ),
            )
        )

    for tool_name in unavailable:
        reason = ""
        for item in resolved:
            if item.entry.name == tool_name:
                reason = item.availability.reason or ""
                break
        findings.append(
            AgentToolAvailabilityFinding(
                tool_name=tool_name,
                severity="warn",
                code="tool_unavailable",
                message=(
                    f"Tool {tool_name!r} is profile-exposed but unavailable"
                    + (f": {reason}" if reason else "")
                ),
            )
        )

    return AgentToolUniverseSnapshot(
        snapshot_id=snapshot_id,
        profile_name=profile_name,
        checked_at=checked_at,
        registered_tools=all_registered,
        profile_exposed_tools=sorted(profile_tool_names),
        model_visible_tools=model_visible,
        hidden_tools=hidden,
        unavailable_tools=unavailable,
        findings=findings,
    )


# ── output_kind classification ──────────────────────────────────────

_OUTPUT_KIND_MAP: dict[str, str] = {
    "read": "context",
    "local_eval": "evidence",
    "append_only_review_write": "artifact",
}


def _classify_output_kind(side_effect: str) -> str:
    return _OUTPUT_KIND_MAP.get(side_effect, "diagnostic")
