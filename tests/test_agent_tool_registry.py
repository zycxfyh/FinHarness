"""Tests for AgentToolRegistry v0.

Agentic-space dimension: Action Space / Tool Surface.
Operating surface: Track A — Agent Tool Surface.
"""

from __future__ import annotations

from finharness.agent_tool_registry import (
    build_registry,
    registered_tools,
    registry_summary,
    tools_by_output_kind,
    tools_by_toolset,
    tools_exposed_to_profile,
)


class TestAgentToolRegistry:
    """Unit tests for AgentToolRegistry v0."""

    # ── build / discovery ─────────────────────────────────────────

    def test_registry_builds_from_live_entries(self) -> None:
        """Registry reads live AGENT_TOOL_ENTRIES and produces registrations."""
        regs = build_registry()
        assert len(regs) == 12
        names = {r.name for r in regs}
        assert "get_capital_context_projection" in names

    def test_registered_tools_returns_names(self) -> None:
        """registered_tools() returns sorted tool names."""
        names = registered_tools()
        assert len(names) == 12
        assert names == sorted(names)

    # ── queries ───────────────────────────────────────────────────

    def test_tools_by_toolset_filters_correctly(self) -> None:
        """tools_by_toolset() returns only matching tools."""
        market = tools_by_toolset("market_data")
        assert len(market) >= 1
        assert all(r.toolset == "market_data" for r in market)

    def test_tools_by_output_kind_context(self) -> None:
        """tools_by_output_kind('context') returns read tools."""
        ctx = tools_by_output_kind("context")
        assert len(ctx) >= 1
        assert all(r.side_effect == "read" for r in ctx)

    def test_tools_exposed_to_default_profile(self) -> None:
        """Default profile exposes base read/explain tools."""
        exposed = tools_exposed_to_profile("default")
        names = {r.name for r in exposed}
        assert "get_capital_context_projection" in names
        assert all("default" in r.profile_allowlist for r in exposed)

    def test_tools_exposed_to_review_draft_profile(self) -> None:
        """Review-draft profile exposes proposal draft tools."""
        exposed = tools_exposed_to_profile("review-draft")
        names = {r.name for r in exposed}
        assert "draft_governed_proposal_from_context" in names
        assert all("review-draft" in r.profile_allowlist for r in exposed)

    # ── invariants ────────────────────────────────────────────────

    def test_all_registrations_have_execution_allowed_false(self) -> None:
        """No tool registration ever grants execution authority."""
        regs = build_registry()
        for r in regs:
            assert r.execution_allowed is False, f"{r.name} has execution_allowed=True"

    def test_all_registrations_have_authority_transition_false(self) -> None:
        """No tool registration ever grants authority transitions."""
        regs = build_registry()
        for r in regs:
            assert r.authority_transition is False, (
                f"{r.name} has authority_transition=True"
            )

    def test_visibility_chain_never_allows_execution(self) -> None:
        """Every registration's visibility chain has execution_authorized=False."""
        regs = build_registry()
        for r in regs:
            chain = r.visibility_chain()
            assert chain["execution_authorized"] is False
            assert chain["authority_eligible"] is False
            assert chain["registered"] is True

    # ── model ─────────────────────────────────────────────────────

    def test_registration_model_is_frozen(self) -> None:
        """AgentToolRegistration is immutable."""
        import pytest
        from pydantic import ValidationError

        reg = build_registry()[0]
        with pytest.raises(ValidationError, match="frozen"):
            reg.name = "hijacked"  # type: ignore[misc]

    def test_registration_has_required_fields(self) -> None:
        """Every registration populates core fields."""
        for r in build_registry():
            assert r.name, f"{r.name}: name empty"
            assert r.toolset, f"{r.name}: toolset empty"
            assert r.description, f"{r.name}: description empty"
            assert r.side_effect in ("read", "local_eval", "append_only_review_write"), (
                f"{r.name}: unexpected side_effect {r.side_effect}"
            )
            assert r.output_kind in (
                "context", "evidence", "artifact", "message", "diagnostic",
            ), f"{r.name}: unexpected output_kind {r.output_kind}"

    # ── summary ───────────────────────────────────────────────────

    def test_registry_summary_is_consistent(self) -> None:
        """registry_summary() matches build_registry() counts."""
        summary = registry_summary()
        regs = build_registry()
        assert summary["total_registered"] == len(regs)
        assert summary["execution_authorized_count"] == 0
        by_toolset = summary["by_toolset"]
        assert isinstance(by_toolset, dict)
        by_toolset_total = sum(int(v) for v in by_toolset.values())
        assert by_toolset_total == len(regs)

    # ── non_claims ────────────────────────────────────────────────

    def test_registration_non_claims(self) -> None:
        """Each registration carries non_claims."""
        reg = build_registry()[0]
        claims = reg.non_claims()
        assert any("execution authority" in c for c in claims)
