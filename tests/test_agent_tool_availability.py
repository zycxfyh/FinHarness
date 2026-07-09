"""Tests for AgentToolAvailabilitySnapshot.

Agentic-space dimension: Action Space / Tool Surface.
Operating surface: Track A — Agent Tool Surface.
"""

from __future__ import annotations

from finharness.agent_tool_availability import (
    capture_tool_availability_snapshots,
    snapshot_for_tool,
)


class TestAgentToolAvailabilitySnapshot:
    """Unit tests for tool availability snapshots."""

    def test_capture_produces_snapshots_for_default_profile(self) -> None:
        """Default profile snapshot covers all resolved tools."""
        snapset = capture_tool_availability_snapshots("default")
        assert len(snapset.snapshots) >= 1
        names = {s.tool_name for s in snapset.snapshots}
        assert "get_capital_context_projection" in names

    def test_available_read_tool_is_available_and_exposed(self) -> None:
        """Read-only context tool is both exposed and available."""
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
        """Proposal draft tool is append_only_review_write with output_kind=artifact."""
        snapset = capture_tool_availability_snapshots("review-draft")
        draft_snap = next(
            s for s in snapset.snapshots
            if s.tool_name == "draft_governed_proposal_from_context"
        )
        assert draft_snap.side_effect == "append_only_review_write"
        assert draft_snap.output_kind == "artifact"
        assert draft_snap.registered is True

    def test_snapshot_for_tool_finds_existing(self) -> None:
        """snapshot_for_tool returns a snapshot for a known tool."""
        snap = snapshot_for_tool("default", "get_quote_snapshot")
        assert snap is not None
        assert snap.tool_name == "get_quote_snapshot"
        assert snap.registered is True

    def test_snapshot_for_tool_returns_none_for_unknown(self) -> None:
        """snapshot_for_tool returns None for an unregistered tool."""
        snap = snapshot_for_tool("default", "nonexistent_tool")
        assert snap is None

    # ── invariants ────────────────────────────────────────────────

    def test_all_snapshots_have_execution_allowed_false(self) -> None:
        """No snapshot ever reports execution_allowed=True."""
        snapset = capture_tool_availability_snapshots("default")
        for s in snapset.snapshots:
            assert s.execution_allowed is False, f"{s.tool_name}: execution_allowed=True"

    def test_all_snapshots_have_authority_transition_false(self) -> None:
        """No snapshot ever reports authority_transition=True."""
        snapset = capture_tool_availability_snapshots("default")
        for s in snapset.snapshots:
            assert s.authority_transition is False

    def test_snapshot_set_summary_is_false_for_execution(self) -> None:
        """Snapshot set summary has execution_allowed=False."""
        snapset = capture_tool_availability_snapshots("default")
        assert snapset.execution_allowed is False
        assert snapset.summary["execution_allowed"] is False

    # ── model ─────────────────────────────────────────────────────

    def test_snapshot_model_is_frozen(self) -> None:
        """AgentToolAvailabilitySnapshot is immutable."""
        import pytest
        from pydantic import ValidationError

        snapset = capture_tool_availability_snapshots("default")
        snap = snapset.snapshots[0]
        with pytest.raises(ValidationError, match="frozen"):
            snap.available = False  # type: ignore[misc]

    def test_snapshot_set_is_frozen(self) -> None:
        """AgentToolAvailabilitySnapshotSet is immutable."""
        import pytest
        from pydantic import ValidationError

        snapset = capture_tool_availability_snapshots("default")
        with pytest.raises(ValidationError, match="frozen"):
            snapset.summary = {}  # type: ignore[misc]

    # ── cross-profile ─────────────────────────────────────────────

    def test_review_draft_profile_exposes_writing_tools(self) -> None:
        """Review-draft profile exposes append-only review write tools."""
        snapset = capture_tool_availability_snapshots("review-draft")
        writing = [
            s for s in snapset.snapshots
            if s.side_effect == "append_only_review_write"
        ]
        for s in writing:
            assert s.exposed is True
            assert s.execution_allowed is False
