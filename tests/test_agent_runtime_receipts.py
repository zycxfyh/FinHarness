"""Tests for AgentRuntime -> AgentRunReceipt bridge.

Agentic-space dimension: Trace Space / Runtime Integration.

v0.1 (PR #209): Adds AgentRuntimeTraceSink tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from finharness.agent_runtime import AgentToolRuntimeError, AgentToolRuntimeResult
from finharness.agent_runtime_receipts import (
    AgentRuntimeTraceSink,
    build_agent_run_receipt_from_runtime_results,
)


class TestBuildAgentRunReceiptFromRuntimeResults:
    """Unit tests for the runtime -> receipt bridge (existing)."""

    def test_single_successful_result_writes_receipt(self) -> None:
        runtime_results = [
            AgentToolRuntimeResult(
                ok=True, tool_name="get_capital_context_projection", side_effect="read",
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
            assert len(receipt.tool_calls) == 1

    def test_multiple_successful_results_writes_receipt(self) -> None:
        runtime_results = [
            AgentToolRuntimeResult(ok=True, tool_name="a", side_effect="read"),
            AgentToolRuntimeResult(ok=True, tool_name="b", side_effect="read"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Check", profile_name="default", runtime_results=runtime_results,
                receipt_root=Path(tmp),
            )
            assert receipt.outcome == "succeeded"
            assert len(receipt.tool_calls) == 2

    def test_all_failed_produces_failed_outcome(self) -> None:
        runtime_results = [
            AgentToolRuntimeResult(
                ok=False, tool_name="x", side_effect="read",
                error=AgentToolRuntimeError(code="HANDLER_FAILED", message="e", recoverable=True),
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Test", profile_name="default", runtime_results=runtime_results,
                receipt_root=Path(tmp),
            )
            assert receipt.outcome == "failed"

    def test_empty_runtime_results_raises(self) -> None:
        with (
            tempfile.TemporaryDirectory() as tmp,
            pytest.raises(ValueError, match="must not be empty"),
        ):
            build_agent_run_receipt_from_runtime_results(
                goal="Test", profile_name="default", runtime_results=[],
                receipt_root=Path(tmp),
            )

    def test_receipt_always_has_execution_allowed_false(self) -> None:
        runtime_results = [AgentToolRuntimeResult(ok=True, tool_name="x", side_effect="read")]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Test", profile_name="default", runtime_results=runtime_results,
                receipt_root=Path(tmp),
            )
            assert receipt.execution_allowed is False

    def test_context_refs_passed_through(self) -> None:
        runtime_results = [AgentToolRuntimeResult(ok=True, tool_name="x", side_effect="read")]
        with tempfile.TemporaryDirectory() as tmp:
            receipt = build_agent_run_receipt_from_runtime_results(
                goal="Test", profile_name="default", runtime_results=runtime_results,
                receipt_root=Path(tmp), context_refs=["capital_summary", "current_ips"],
            )
            assert "capital_summary" in receipt.context_refs


class TestAgentRuntimeTraceSink:
    """Tests for AgentRuntimeTraceSink (new in v0.1)."""

    def test_sink_dispatch_records_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = AgentRuntimeTraceSink(
                goal="Test goal", profile_name="default", receipt_root=tmp,
            )
            result = sink.dispatch(
                profile_name="default",
                tool_name="get_quote_snapshot",
                arguments={"symbol": "AAPL"},
            )
            assert result.ok is True
            assert sink.result_count == 1

    def test_sink_dispatch_records_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = AgentRuntimeTraceSink(
                goal="Test goal", profile_name="default", receipt_root=tmp,
            )
            result = sink.dispatch(
                profile_name="default",
                tool_name="nonexistent_tool",
                arguments={},
            )
            assert result.ok is False
            assert sink.result_count == 1  # Failed dispatch still recorded

    def test_sink_finalize_writes_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = AgentRuntimeTraceSink(
                goal="Multi-dispatch test", profile_name="default", receipt_root=tmp,
            )
            a = {"symbol": "AAPL"}
            g = {"symbol": "GOOGL"}
            sink.dispatch(profile_name="default", tool_name="get_quote_snapshot", arguments=a)
            sink.dispatch(profile_name="default", tool_name="get_quote_snapshot", arguments=g)
            assert sink.result_count == 2
            receipt = sink.finalize()
            assert receipt.goal == "Multi-dispatch test"
            assert len(receipt.tool_calls) == 2
            assert receipt.outcome == "succeeded"

    def test_sink_finalize_twice_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = AgentRuntimeTraceSink(
                goal="Test", profile_name="default", receipt_root=tmp,
            )
            sink.dispatch(
                profile_name="default",
                tool_name="get_capital_context_projection",
                arguments={"open_proposals_limit": 5},
            )
            sink.finalize()
            with pytest.raises(RuntimeError, match=r"finalize.*already called"):
                sink.finalize()

    def test_sink_record_after_finalize_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = AgentRuntimeTraceSink(
                goal="Test", profile_name="default", receipt_root=tmp,
            )
            sink.dispatch(
                profile_name="default",
                tool_name="get_quote_snapshot",
                arguments={"symbol": "AAPL"},
            )
            sink.finalize()
            with pytest.raises(RuntimeError, match="cannot record_result after finalize"):
                sink.record_result(
                    AgentToolRuntimeResult(ok=True, tool_name="x", side_effect="read")
                )

    def test_sink_finalize_empty_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sink = AgentRuntimeTraceSink(goal="Test", profile_name="default", receipt_root=tmp)
            with pytest.raises(ValueError, match="no dispatch results"):
                sink.finalize()

    def test_sink_empty_goal_raises(self) -> None:
        with pytest.raises(ValueError, match="goal must not be empty"):
            AgentRuntimeTraceSink(goal="  ", profile_name="d", receipt_root="/tmp")

    def test_sink_multiple_failures_all_recorded(self) -> None:
        """All failed dispatches are still recorded and produce a failed receipt."""
        with tempfile.TemporaryDirectory() as tmp:
            sink = AgentRuntimeTraceSink(goal="All fail", profile_name="default", receipt_root=tmp)
            sink.dispatch(profile_name="default", tool_name="nonexistent", arguments={})
            sink.dispatch(profile_name="default", tool_name="also_missing", arguments={})
            assert sink.result_count == 2
            receipt = sink.finalize()
            assert receipt.outcome == "failed"
            assert len(receipt.tool_calls) == 2
