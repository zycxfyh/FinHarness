"""Tests for AgentRuntime → AgentRunReceipt bridge.

Agentic-space dimension: Trace Space / Runtime Integration.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from finharness.agent_runtime import AgentToolRuntimeError, AgentToolRuntimeResult
from finharness.agent_runtime_receipts import build_agent_run_receipt_from_runtime_results


class TestBuildAgentRunReceiptFromRuntimeResults:
    """Unit tests for the runtime → receipt bridge."""

    # ── success cases ──────────────────────────────────────────

    def test_single_successful_result_writes_receipt(self) -> None:
        """Visible tool success → AgentRunReceipt written."""
        runtime_results = [
            AgentToolRuntimeResult(
                ok=True,
                tool_name="get_capital_context_projection",
                side_effect="read",
                result={"status": "ok"},
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Explain current portfolio exposure",
                profile_name="default",
                runtime_results=runtime_results,
                receipt_root=Path(tmp),
            )
            assert receipt.outcome == "succeeded"
            assert receipt.stop_reason == "runtime_dispatch_complete"
            assert receipt.execution_allowed is False
            assert receipt.authority_transition is False
            assert len(receipt.tool_calls) == 1
            tc = receipt.tool_calls[0]
            assert tc.tool_name == "get_capital_context_projection"
            assert tc.side_effect == "read"
            assert tc.ok is True
            assert tc.error_code is None

    def test_multiple_successful_results_writes_receipt(self) -> None:
        """All ok → outcome=succeeded, execution_allowed=False."""
        runtime_results = [
            AgentToolRuntimeResult(
                ok=True,
                tool_name="get_capital_context_projection",
                side_effect="read",
            ),
            AgentToolRuntimeResult(
                ok=True,
                tool_name="get_quote_snapshot",
                side_effect="read",
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Check portfolio + quote",
                profile_name="default",
                runtime_results=runtime_results,
                receipt_root=Path(tmp),
            )
            assert receipt.outcome == "succeeded"
            assert receipt.execution_allowed is False
            assert receipt.authority_transition is False
            assert len(receipt.tool_calls) == 2

    # ── error / partial cases ──────────────────────────────────

    def test_unavailable_tool_produces_data_gap(self) -> None:
        """Unavailable tool → AgentRunReceipt with data_gaps + outcome=partial."""
        runtime_results = [
            AgentToolRuntimeResult(
                ok=True,
                tool_name="get_capital_context_projection",
                side_effect="read",
            ),
            AgentToolRuntimeResult(
                ok=False,
                tool_name="get_current_ips_context",
                side_effect="read",
                error=AgentToolRuntimeError(
                    code="STATECORE_UNAVAILABLE",
                    message="state-core is unavailable",
                    recoverable=True,
                ),
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Read portfolio and IPS",
                profile_name="default",
                runtime_results=runtime_results,
                receipt_root=Path(tmp),
            )
            assert receipt.outcome == "partial"
            assert "get_current_ips_context: STATECORE_UNAVAILABLE" in receipt.data_gaps
            tc_failed = receipt.tool_calls[1]
            assert tc_failed.ok is False
            assert tc_failed.error_code == "STATECORE_UNAVAILABLE"

    def test_all_failed_produces_failed_outcome(self) -> None:
        """All errors → outcome=failed."""
        runtime_results = [
            AgentToolRuntimeResult(
                ok=False,
                tool_name="get_quote_snapshot",
                side_effect="read",
                error=AgentToolRuntimeError(
                    code="HANDLER_FAILED",
                    message="network error",
                    recoverable=True,
                ),
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Get quote",
                profile_name="default",
                runtime_results=runtime_results,
                receipt_root=Path(tmp),
            )
            assert receipt.outcome == "failed"
            assert "dispatch_failed:" in receipt.stop_reason
            assert receipt.execution_allowed is False

    # ── guard invariants ───────────────────────────────────────

    def test_receipt_always_has_execution_allowed_false(self) -> None:
        """Receipt has execution_allowed=False — no authority granted by trace."""
        runtime_results = [
            AgentToolRuntimeResult(
                ok=True,
                tool_name="get_capital_context_projection",
                side_effect="read",
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Test",
                profile_name="default",
                runtime_results=runtime_results,
                receipt_root=Path(tmp),
            )
            assert receipt.execution_allowed is False
            # Also check the written JSON
            file_path = Path(tmp) / "agent-runs" / f"{receipt.receipt_id}.json"
            payload = json.loads(file_path.read_text())
            assert payload["execution_allowed"] is False

    def test_receipt_always_has_authority_transition_false(self) -> None:
        """Receipt has authority_transition=False — bridge is trace-only."""
        runtime_results = [
            AgentToolRuntimeResult(
                ok=True,
                tool_name="get_capital_context_projection",
                side_effect="read",
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Test",
                profile_name="default",
                runtime_results=runtime_results,
                receipt_root=Path(tmp),
            )
            assert receipt.authority_transition is False
            file_path = Path(tmp) / "agent-runs" / f"{receipt.receipt_id}.json"
            payload = json.loads(file_path.read_text())
            assert payload["authority_transition"] is False

    def test_truncated_result_is_recorded(self) -> None:
        """Truncated result → tool call summary shows result_truncated=True."""
        runtime_results = [
            AgentToolRuntimeResult(
                ok=True,
                tool_name="get_capital_context_projection",
                side_effect="read",
                truncated=True,
                original_result_chars=50000,
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Get context",
                profile_name="default",
                runtime_results=runtime_results,
                receipt_root=Path(tmp),
            )
            tc = receipt.tool_calls[0]
            assert tc.result_truncated is True

    # ── edge cases ─────────────────────────────────────────────

    def test_empty_runtime_results_raises(self) -> None:
        """Empty list raises ValueError."""
        import pytest

        with tempfile.TemporaryDirectory() as tmp, pytest.raises(
            ValueError, match="must not be empty"
        ):
            build_agent_run_receipt_from_runtime_results(
                goal="Test",
                profile_name="default",
                runtime_results=[],
                receipt_root=Path(tmp),
            )

    def test_context_refs_passed_through(self) -> None:
        """context_refs are forwarded to the receipt."""
        runtime_results = [
            AgentToolRuntimeResult(
                ok=True,
                tool_name="get_capital_context_projection",
                side_effect="read",
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Test",
                profile_name="default",
                runtime_results=runtime_results,
                receipt_root=Path(tmp),
                context_refs=["capital_summary", "current_ips"],
            )
            assert "capital_summary" in receipt.context_refs
            assert "current_ips" in receipt.context_refs
