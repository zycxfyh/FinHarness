"""Tests for AgentToolResultEnvelope.

Agentic-space dimension: Trace Space / Evidence Space.
Operating surface: Track B — Evidence / Runtime Envelope.
"""

from __future__ import annotations

from finharness.agent_runtime import AgentToolRuntimeError, AgentToolRuntimeResult
from finharness.agent_tool_result_envelope import (
    build_tool_result_envelope,
    build_tool_result_envelopes,
)


class TestAgentToolResultEnvelope:
    """Unit tests for AgentToolResultEnvelope."""

    def test_read_tool_envelope_has_context_output_kind(self) -> None:
        """Read-only context tool → output_kind=context, source refs present."""
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
        """Failed tool → data_gaps populated, ok=False."""
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
        """Every envelope has execution_allowed=False."""
        rt = AgentToolRuntimeResult(
            ok=True,
            tool_name="get_quote_snapshot",
            side_effect="read",
        )
        env = build_tool_result_envelope(rt)
        assert env.execution_allowed is False
        assert env.authority_transition is False

    def test_envelope_preserves_truncated_flag(self) -> None:
        """Truncated results carry truncated=True."""
        rt = AgentToolRuntimeResult(
            ok=True,
            tool_name="get_capital_context_projection",
            side_effect="read",
            truncated=True,
        )
        env = build_tool_result_envelope(rt)
        assert env.truncated is True

    def test_batch_envelopes_preserves_count(self) -> None:
        """Batch builder produces one envelope per runtime result."""
        results = [
            AgentToolRuntimeResult(ok=True, tool_name="a", side_effect="read"),
            AgentToolRuntimeResult(ok=True, tool_name="b", side_effect="read"),
        ]
        envelopes = build_tool_result_envelopes(results)
        assert len(envelopes) == 2
        assert envelopes[0].tool_name == "a"
        assert envelopes[1].tool_name == "b"

    # ── invariants ────────────────────────────────────────────────

    def test_envelope_model_is_frozen(self) -> None:
        """AgentToolResultEnvelope is immutable."""
        import pytest
        from pydantic import ValidationError

        rt = AgentToolRuntimeResult(
            ok=True,
            tool_name="get_quote_snapshot",
            side_effect="read",
        )
        env = build_tool_result_envelope(rt)
        with pytest.raises(ValidationError, match="frozen"):
            env.ok = False  # type: ignore[misc]

    # ── output_kind classification ────────────────────────────────

    def test_local_eval_tool_has_evidence_output_kind(self) -> None:
        """Local eval tool → output_kind=evidence."""
        rt = AgentToolRuntimeResult(
            ok=True,
            tool_name="evaluate_latest_risk_note",
            side_effect="local_eval",
        )
        env = build_tool_result_envelope(rt)
        assert env.output_kind == "evidence"

    def test_review_write_tool_has_artifact_output_kind(self) -> None:
        """Append-only review write → output_kind=artifact."""
        rt = AgentToolRuntimeResult(
            ok=True,
            tool_name="draft_governed_proposal_from_context",
            side_effect="append_only_review_write",
        )
        env = build_tool_result_envelope(rt)
        assert env.output_kind == "artifact"
        assert env.execution_allowed is False
