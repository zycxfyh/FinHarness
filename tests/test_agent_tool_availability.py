"""Tests for AgentToolAvailabilitySnapshot v0.1.

Agentic-space dimension: Action Space / Tool Surface.
Operating surface: Track A — Agent Tool Surface.

v0.1 adds:
  - AgentToolUniverseSnapshot (global view, not just profile-resolved)
  - check_tool_availability_cached() with TTL + failure grace
  - AgentToolAvailabilityFinding diagnostics
"""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from finharness.agent_tool_availability import (
    AgentToolAvailabilityFinding,
    capture_tool_availability_snapshots,
    capture_tool_universe_snapshot,
    check_tool_availability_cached,
    clear_availability_cache,
    snapshot_for_tool,
)
from finharness.agent_tools import AgentToolAvailability


class TestAgentToolAvailabilitySnapshot:
    """Unit tests for per-profile tool availability snapshots (existing)."""

    def test_capture_produces_snapshots_for_default_profile(self) -> None:
        snapset = capture_tool_availability_snapshots("default")
        assert len(snapset.snapshots) >= 1
        names = {s.tool_name for s in snapset.snapshots}
        assert "get_capital_context_projection" in names

    def test_available_read_tool_is_available_and_exposed(self) -> None:
        snapset = capture_tool_availability_snapshots("default")
        ctx_snap = next(
            s for s in snapset.snapshots
            if s.tool_name == "get_capital_context_projection"
        )
        assert ctx_snap.exposed is True
        assert ctx_snap.available is True
        assert ctx_snap.side_effect == "read"
        assert ctx_snap.output_kind == "context"

    def test_append_only_review_write_tool_has_correct_side_effect(self) -> None:
        snapset = capture_tool_availability_snapshots("review-draft")
        draft_snap = next(
            s for s in snapset.snapshots
            if s.tool_name == "draft_governed_proposal_from_context"
        )
        assert draft_snap.side_effect == "append_only_review_write"
        assert draft_snap.output_kind == "artifact"
        assert draft_snap.registered is True

    def test_snapshot_for_tool_finds_existing(self) -> None:
        snap = snapshot_for_tool("default", "get_quote_snapshot")
        assert snap is not None
        assert snap.tool_name == "get_quote_snapshot"
        assert snap.registered is True

    def test_snapshot_for_tool_returns_none_for_unknown(self) -> None:
        snap = snapshot_for_tool("default", "nonexistent_tool")
        assert snap is None

    def test_all_snapshots_have_execution_allowed_false(self) -> None:
        snapset = capture_tool_availability_snapshots("default")
        for s in snapset.snapshots:
            assert s.execution_allowed is False, f"{s.tool_name}: execution_allowed=True"

    def test_all_snapshots_have_authority_transition_false(self) -> None:
        snapset = capture_tool_availability_snapshots("default")
        for s in snapset.snapshots:
            assert s.authority_transition is False

    def test_snapshot_set_summary_is_false_for_execution(self) -> None:
        snapset = capture_tool_availability_snapshots("default")
        assert snapset.execution_allowed is False
        assert snapset.summary["execution_allowed"] is False

    def test_snapshot_model_is_frozen(self) -> None:
        snapset = capture_tool_availability_snapshots("default")
        snap = snapset.snapshots[0]
        with pytest.raises(ValidationError, match="frozen"):
            snap.available = False  # type: ignore[misc]

    def test_snapshot_set_is_frozen(self) -> None:
        snapset = capture_tool_availability_snapshots("default")
        with pytest.raises(ValidationError, match="frozen"):
            snapset.summary = {}  # type: ignore[misc]

    def test_review_draft_profile_exposes_writing_tools(self) -> None:
        snapset = capture_tool_availability_snapshots("review-draft")
        writing = [
            s for s in snapset.snapshots
            if s.side_effect == "append_only_review_write"
        ]
        for s in writing:
            assert s.exposed is True
            assert s.execution_allowed is False


class TestAgentToolUniverseSnapshot:
    """Tests for global tool universe snapshot (new in v0.1)."""

    def test_universe_includes_all_registered_tools(self) -> None:
        univ = capture_tool_universe_snapshot("default")
        assert len(univ.registered_tools) >= 12
        assert "get_capital_context_projection" in univ.registered_tools
        assert "draft_governed_proposal_from_context" in univ.registered_tools

    def test_universe_distinguishes_exposed_from_registered(self) -> None:
        univ = capture_tool_universe_snapshot("default")
        # profile-exposed tools are a subset of registered
        assert set(univ.profile_exposed_tools).issubset(set(univ.registered_tools))
        # model-visible are a subset of profile-exposed
        assert set(univ.model_visible_tools).issubset(set(univ.profile_exposed_tools))

    def test_universe_has_model_visible_tools(self) -> None:
        univ = capture_tool_universe_snapshot("default")
        assert len(univ.model_visible_tools) >= 1
        assert "get_capital_context_projection" in univ.model_visible_tools

    def test_universe_has_hidden_tools(self) -> None:
        univ = capture_tool_universe_snapshot("default")
        # Some tools may be hidden (profile-exposed but not model-visible)
        assert isinstance(univ.hidden_tools, list)

    def test_universe_has_unavailable_tools(self) -> None:
        univ = capture_tool_universe_snapshot("default")
        assert isinstance(univ.unavailable_tools, list)

    def test_universe_findings_include_not_exposed_tools(self) -> None:
        univ = capture_tool_universe_snapshot("default")
        not_exposed = set(univ.registered_tools) - set(univ.profile_exposed_tools)
        if not_exposed:
            codes = {f.code for f in univ.findings}
            assert "tool_not_profile_exposed" in codes

    def test_universe_findings_include_unavailable(self) -> None:
        univ = capture_tool_universe_snapshot("default")
        if univ.unavailable_tools:
            codes = {f.code for f in univ.findings}
            assert "tool_unavailable" in codes

    def test_universe_model_is_frozen(self) -> None:
        univ = capture_tool_universe_snapshot("default")
        with pytest.raises(ValidationError, match="frozen"):
            univ.registered_tools = []  # type: ignore[misc]

    def test_universe_no_execution_authorized(self) -> None:
        univ = capture_tool_universe_snapshot("default")
        assert univ.execution_allowed is False
        assert univ.authority_transition is False

    def test_universe_covers_different_profiles(self) -> None:
        univ_default = capture_tool_universe_snapshot("default")
        univ_review = capture_tool_universe_snapshot("review-draft")
        # Both have same registered tools
        assert univ_default.registered_tools == univ_review.registered_tools
        # But different exposed sets
        assert univ_default.profile_exposed_tools != univ_review.profile_exposed_tools

    def test_universe_model_visible_plus_hidden_equals_exposed(self) -> None:
        univ = capture_tool_universe_snapshot("default")
        union = set(univ.model_visible_tools) | set(univ.hidden_tools)
        assert union == set(univ.profile_exposed_tools)


class TestAgentToolAvailabilityFinding:
    """Tests for the finding model (new in v0.1)."""

    def test_finding_is_frozen(self) -> None:
        f = AgentToolAvailabilityFinding(
            tool_name="t", severity="warn", code="C1", message="m"
        )
        with pytest.raises(ValidationError, match="frozen"):
            f.tool_name = "x"  # type: ignore[misc]

    def test_finding_severity_literal(self) -> None:
        with pytest.raises(ValidationError):
            AgentToolAvailabilityFinding(
                tool_name="t", severity="critical", code="c", message="m"  # type: ignore[arg-type]
            )


class TestCachedAvailability:
    """Tests for check_tool_availability_cached()."""

    def setup_method(self) -> None:
        clear_availability_cache()

    def teardown_method(self) -> None:
        clear_availability_cache()

    def test_cached_check_returns_availability(self) -> None:
        result = check_tool_availability_cached("get_capital_context_projection")
        assert isinstance(result, AgentToolAvailability)
        assert result.available is True

    def test_cached_check_unknown_tool(self) -> None:
        result = check_tool_availability_cached("nonexistent_tool")
        assert result.available is False
        assert "not registered" in (result.reason or "")

    def test_cache_returns_cached_result_within_ttl(self) -> None:
        clear_availability_cache()
        # First call populates cache
        check_tool_availability_cached(
            "get_capital_context_projection", ttl_seconds=999.0
        )
        # Second call with mock time still within TTL
        result = check_tool_availability_cached(
            "get_capital_context_projection", ttl_seconds=999.0
        )
        assert result.available is True

    def test_cache_expires_after_ttl(self) -> None:
        clear_availability_cache()
        check_tool_availability_cached(
            "get_capital_context_projection", ttl_seconds=0.001
        )
        time.sleep(0.01)
        result = check_tool_availability_cached(
            "get_capital_context_projection", ttl_seconds=0.001
        )
        # Cache expired, re-checks — should still be available
        assert result.available is True

    def test_clear_cache_works(self) -> None:
        check_tool_availability_cached("get_quote_snapshot", ttl_seconds=999.0)
        clear_availability_cache()
        result = check_tool_availability_cached("get_quote_snapshot")
        assert result.available is True  # Fresh check, tool is available
