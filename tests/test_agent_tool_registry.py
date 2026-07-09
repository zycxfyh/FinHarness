"""Tests for AgentToolRegistry v0.1 — runtime-authoritative metadata.

Agentic-space dimension: Action Space / Tool Surface.
Operating surface: Track A — Agent Tool Surface.
"""

from __future__ import annotations

import pytest

from finharness.agent_tool_registry import (
    AgentToolRegistry,
    AgentToolRegistryFinding,
    build_registry,
    registered_tools,
    registry_summary,
    tools_by_output_kind,
    tools_by_toolset,
    tools_exposed_to_profile,
)


class TestAgentToolRegistry:
    """Unit tests for AgentToolRegistry v0.1."""

    # ── build / discovery ─────────────────────────────────────────

    def test_registry_builds_from_live_entries(self) -> None:
        """Registry reads live AGENT_TOOL_ENTRIES and produces registrations."""
        registry = build_registry()
        assert isinstance(registry, AgentToolRegistry)
        assert registry.total_count == 12
        assert registry.invalid_count == 0
        names = set(registry.registrations)
        assert "get_capital_context_projection" in names

    def test_registry_registrations_is_dict_keyed_by_name(self) -> None:
        """registrations dict uses tool name as key."""
        registry = build_registry()
        for name, reg in registry.registrations.items():
            assert reg.name == name, f"key {name!r} != reg.name {reg.name!r}"

    def test_registered_tools_returns_names(self) -> None:
        """registered_tools() returns sorted tool names."""
        names = registered_tools()
        assert len(names) == 12
        assert names == sorted(names)

    def test_registry_registered_tools_property(self) -> None:
        """registry.registered_tools matches free function."""
        registry = build_registry()
        assert registry.registered_tools == registered_tools()

    def test_registry_generation_is_1(self) -> None:
        """First registry build has generation=1."""
        registry = build_registry()
        assert registry.generation == 1

    def test_registry_findings_empty_on_clean_build(self) -> None:
        """No findings when all entries convert cleanly."""
        registry = build_registry(strict=False)
        assert registry.findings == []
        assert registry.invalid_count == 0

    # ── strict mode ──────────────────────────────────────────────

    def test_strict_true_is_default(self) -> None:
        """build_registry() defaults to strict=True."""
        registry = build_registry()
        assert registry.total_count == 12

    def test_strict_false_allows_partial_registry(self) -> None:
        """strict=False records findings, does not raise."""
        registry = build_registry(strict=False)
        assert isinstance(registry, AgentToolRegistry)
        assert registry.findings == []

    # ── queries ───────────────────────────────────────────────────

    def test_tools_by_toolset_filters_correctly(self) -> None:
        """tools_by_toolset() returns only matching tools."""
        market = tools_by_toolset("market_data")
        assert len(market) >= 1
        assert all(r.toolset == "market_data" for r in market)

    def test_registry_tools_by_toolset(self) -> None:
        """registry.tools_by_toolset() matches free function."""
        registry = build_registry()
        assert len(registry.tools_by_toolset("market_data")) >= 1

    def test_tools_by_output_kind_context(self) -> None:
        """tools_by_output_kind('context') returns read tools."""
        ctx = tools_by_output_kind("context")
        assert len(ctx) >= 1
        assert all(r.side_effect == "read" for r in ctx)

    def test_registry_tools_by_output_kind(self) -> None:
        """registry.tools_by_output_kind() matches free function."""
        registry = build_registry()
        assert len(registry.tools_by_output_kind("context")) >= 1

    def test_tools_exposed_to_default_profile(self) -> None:
        """Default profile exposes base read/explain tools."""
        exposed = tools_exposed_to_profile("default")
        names = {r.name for r in exposed}
        assert "get_capital_context_projection" in names
        assert all("default" in r.profile_allowlist for r in exposed)

    def test_registry_tools_exposed_to_profile(self) -> None:
        """registry.tools_exposed_to_profile() matches free function."""
        registry = build_registry()
        exposed = registry.tools_exposed_to_profile("default")
        assert len(exposed) >= 1

    def test_tools_exposed_to_review_draft_profile(self) -> None:
        """Review-draft profile exposes proposal draft tools."""
        exposed = tools_exposed_to_profile("review-draft")
        names = {r.name for r in exposed}
        assert "draft_governed_proposal_from_context" in names
        assert all("review-draft" in r.profile_allowlist for r in exposed)

    # ── invariants ────────────────────────────────────────────────

    def test_all_registrations_have_execution_allowed_false(self) -> None:
        """No tool registration ever grants execution authority."""
        registry = build_registry()
        for r in registry.registrations.values():
            assert r.execution_allowed is False, f"{r.name} has execution_allowed=True"

    def test_all_registrations_have_authority_transition_false(self) -> None:
        """No tool registration ever grants authority transitions."""
        registry = build_registry()
        for r in registry.registrations.values():
            assert r.authority_transition is False, (
                f"{r.name} has authority_transition=True"
            )

    def test_visibility_chain_never_allows_execution(self) -> None:
        """Every registration's visibility chain has execution_authorized=False."""
        registry = build_registry()
        for r in registry.registrations.values():
            chain = r.visibility_chain()
            assert chain["execution_authorized"] is False
            assert chain["authority_eligible"] is False
            assert chain["registered"] is True

    # ── model ─────────────────────────────────────────────────────

    def test_registration_model_is_frozen(self) -> None:
        """AgentToolRegistration is immutable."""
        from pydantic import ValidationError

        registry = build_registry()
        reg = next(iter(registry.registrations.values()))
        with pytest.raises(ValidationError, match="frozen"):
            reg.name = "hijacked"  # type: ignore[misc]

    def test_registry_object_is_frozen(self) -> None:
        """AgentToolRegistry itself is immutable."""
        from pydantic import ValidationError

        registry = build_registry()
        with pytest.raises(ValidationError, match="frozen"):
            registry.generation = 2  # type: ignore[misc]

    def test_registration_has_required_fields(self) -> None:
        """Every registration populates core fields."""
        for r in build_registry().registrations.values():
            assert r.name, f"{r.name}: name empty"
            assert r.toolset, f"{r.name}: toolset empty"
            assert r.description, f"{r.name}: description empty"
            assert r.side_effect in ("read", "local_eval", "append_only_review_write"), (
                f"{r.name}: unexpected side_effect {r.side_effect}"
            )
            assert r.output_kind in (
                "context", "evidence", "artifact", "message", "diagnostic",
            ), f"{r.name}: unexpected output_kind {r.output_kind}"

    # ── findings model ────────────────────────────────────────────

    def test_finding_model_is_frozen(self) -> None:
        """AgentToolRegistryFinding is immutable."""
        from pydantic import ValidationError

        finding = AgentToolRegistryFinding(
            tool_name="test_tool",
            severity="block",
            code="test_code",
            message="test message",
        )
        with pytest.raises(ValidationError, match="frozen"):
            finding.tool_name = "hijacked"  # type: ignore[misc]

    def test_finding_severity_is_literal(self) -> None:
        """severity field rejects invalid values."""
        with pytest.raises(Exception):
            AgentToolRegistryFinding(
                tool_name="t",
                severity="critical",  # type: ignore[arg-type]
                code="c",
                message="m",
            )

    # ── summary ───────────────────────────────────────────────────

    def test_registry_summary_is_consistent(self) -> None:
        """registry_summary() matches registry.total_count."""
        summary = registry_summary()
        registry = build_registry()
        assert summary["total_registered"] == registry.total_count
        assert summary["invalid_count"] == 0
        assert summary["execution_authorized_count"] == 0
        by_toolset = summary["by_toolset"]
        assert isinstance(by_toolset, dict)
        by_toolset_total = sum(int(v) for v in by_toolset.values())
        assert by_toolset_total == registry.total_count

    def test_registry_object_summary(self) -> None:
        """registry.summary() matches free function."""
        registry = build_registry()
        assert registry.summary()["total_registered"] == 12
        assert "invalid_count" in registry.summary()

    # ── non_claims ────────────────────────────────────────────────

    def test_registration_non_claims(self) -> None:
        """Each registration carries non_claims."""
        registry = build_registry()
        reg = next(iter(registry.registrations.values()))
        claims = reg.non_claims()
        assert any("execution authority" in c for c in claims)
