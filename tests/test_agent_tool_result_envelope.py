"""Tests for AgentToolResultEnvelope v0.1.

Agentic-space dimension: Trace Space / Evidence Space.
Operating surface: Track B — Evidence / Runtime Envelope.

v0.1 (PR #208): provider_refs separated from evidence_refs.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from finharness.agent_runtime import AgentToolRuntimeError, AgentToolRuntimeResult
from finharness.agent_tool_result_envelope import (
    build_tool_result_envelope,
    build_tool_result_envelopes,
)


class TestAgentToolResultEnvelope:
    """Unit tests for AgentToolResultEnvelope v0.1."""

    def test_read_tool_envelope_has_context_output_kind(self) -> None:
        rt = AgentToolRuntimeResult(
            ok=True,
            tool_name="get_capital_context_projection",
            side_effect="read",
            result={"status": "ok"},
        )
        env = build_tool_result_envelope(rt)
        assert env.ok is True
        assert env.tool_name == "get_capital_context_projection"
        assert env.output_kind == "context"
        assert env.side_effect == "read"
        assert env.error_code is None

    def test_failed_tool_envelope_has_data_gaps(self) -> None:
        rt = AgentToolRuntimeResult(
            ok=False,
            tool_name="get_current_ips_context",
            side_effect="read",
            error=AgentToolRuntimeError(
                code="STATECORE_UNAVAILABLE",
                message="state-core unavailable",
                recoverable=True,
            ),
        )
        env = build_tool_result_envelope(rt)
        assert env.ok is False
        assert env.error_code == "STATECORE_UNAVAILABLE"
        assert any("STATECORE_UNAVAILABLE" in gap for gap in env.data_gaps)

    def test_envelope_always_has_execution_allowed_false(self) -> None:
        rt = AgentToolRuntimeResult(ok=True, tool_name="get_quote_snapshot", side_effect="read")
        env = build_tool_result_envelope(rt)
        assert env.execution_allowed is False
        assert env.authority_transition is False

    def test_envelope_preserves_truncated_flag(self) -> None:
        rt = AgentToolRuntimeResult(
            ok=True,
            tool_name="get_capital_context_projection",
            side_effect="read",
            truncated=True,
        )
        env = build_tool_result_envelope(rt)
        assert env.truncated is True

    def test_batch_envelopes_preserves_count(self) -> None:
        results = [
            AgentToolRuntimeResult(ok=True, tool_name="a", side_effect="read"),
            AgentToolRuntimeResult(ok=True, tool_name="b", side_effect="read"),
        ]
        envelopes = build_tool_result_envelopes(results)
        assert len(envelopes) == 2
        assert envelopes[0].tool_name == "a"
        assert envelopes[1].tool_name == "b"

    def test_envelope_model_is_frozen(self) -> None:
        rt = AgentToolRuntimeResult(ok=True, tool_name="get_quote_snapshot", side_effect="read")
        env = build_tool_result_envelope(rt)
        with pytest.raises(ValidationError, match="frozen"):
            env.ok = False  # type: ignore[misc]

    def test_local_eval_tool_has_evidence_output_kind(self) -> None:
        rt = AgentToolRuntimeResult(
            ok=True, tool_name="evaluate_latest_risk_note", side_effect="local_eval",
        )
        env = build_tool_result_envelope(rt)
        assert env.output_kind == "evidence"

    def test_review_write_tool_has_artifact_output_kind(self) -> None:
        rt = AgentToolRuntimeResult(
            ok=True,
            tool_name="draft_governed_proposal_from_context",
            side_effect="append_only_review_write",
        )
        env = build_tool_result_envelope(rt)
        assert env.output_kind == "artifact"
        assert env.execution_allowed is False

    # ── ref taxonomy (new in v0.1) ─────────────────────────────────

    def test_provider_refs_separated_from_evidence_refs(self) -> None:
        """provider:yfinance goes to provider_refs, NOT evidence_refs."""
        # Dispatch a real tool that has provider_ids
        from finharness.agent_runtime import dispatch_agent_tool

        rt = dispatch_agent_tool(
            profile_name="default",
            tool_name="get_quote_snapshot",
            arguments={"symbol": "AAPL"},
        )
        env = build_tool_result_envelope(rt)
        # Provider refs carry provider metadata
        assert isinstance(env.provider_refs, list)
        # Evidence refs must NOT contain provider: prefix
        for ref in env.evidence_refs:
            assert not ref.startswith("provider:"), (
                f"evidence_refs contains provider ref: {ref}"
            )

    def test_provider_refs_never_appear_in_evidence_refs(self) -> None:
        """No provider: prefixed ref leaks into evidence_refs."""
        from finharness.agent_runtime import dispatch_agent_tool

        rt = dispatch_agent_tool(
            profile_name="default",
            tool_name="get_quote_snapshot",
            arguments={"symbol": "AAPL"},
        )
        env = build_tool_result_envelope(rt)
        all_evidence = set(env.evidence_refs)
        for pr in env.provider_refs:
            assert pr not in all_evidence, (
                f"provider_ref {pr!r} leaked into evidence_refs"
            )

    def test_envelope_has_new_ref_fields(self) -> None:
        """New fields provider_refs and observation_refs exist and are lists."""
        rt = AgentToolRuntimeResult(ok=True, tool_name="t", side_effect="read")
        env = build_tool_result_envelope(rt)
        assert env.provider_refs == []
        assert env.observation_refs == []
        assert isinstance(env.provider_refs, list)
        assert isinstance(env.observation_refs, list)

    def test_evidence_refs_are_receipt_refs(self) -> None:
        """evidence_refs should contain receipt refs, not provider IDs."""
        from finharness.agent_runtime import dispatch_agent_tool

        rt = dispatch_agent_tool(
            profile_name="review-draft",
            tool_name="draft_governed_proposal_from_context",
            arguments={"goal": "test"},
        )
        env = build_tool_result_envelope(rt)
        # Evidence refs = receipt refs (concrete evidence)
        for ref in env.evidence_refs:
            assert not ref.startswith("provider:"), (
                f"evidence_refs has provider ref: {ref}"
            )
