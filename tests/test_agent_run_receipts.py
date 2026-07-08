"""Tests for AgentRunReceipt v0."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pydantic import ValidationError

from finharness.agent_run_receipts import (
    AgentToolCallSummary,
    write_agent_run_receipt,
)


class TestAgentRunReceipt:
    """Unit tests for AgentRunReceipt model and writer."""

    def test_write_agent_run_receipt_creates_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = write_agent_run_receipt(
                goal="Explain current portfolio exposure",
                profile_name="default",
                tool_calls=[
                    AgentToolCallSummary(
                        tool_name="get_capital_context_projection",
                        side_effect="read",
                        ok=True,
                    ),
                ],
                outcome="succeeded",
                stop_reason="goal_met",
                receipt_root=root,
            )
            file_path = root / "agent-runs" / f"{receipt.receipt_id}.json"
            assert file_path.exists()
            payload = json.loads(file_path.read_text())
            assert payload["goal"] == "Explain current portfolio exposure"
            assert payload["profile_name"] == "default"
            assert payload["outcome"] == "succeeded"
            assert payload["execution_allowed"] is False
            assert payload["authority_transition"] is False

    def test_agent_run_receipt_collects_tool_call_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_agent_run_receipt(
                goal="Check risk metrics for AAPL",
                profile_name="review-draft",
                tool_calls=[
                    AgentToolCallSummary(
                        tool_name="get_historical_risk_metrics",
                        side_effect="read",
                        ok=True,
                        evidence_refs=["market_data.yfinance"],
                        receipt_refs=["r_abc123"],
                    ),
                    AgentToolCallSummary(
                        tool_name="evaluate_latest_risk_note",
                        side_effect="local_eval",
                        ok=True,
                        evidence_refs=["local_eval.promptfoo"],
                    ),
                ],
                outcome="succeeded",
                stop_reason="goal_met",
                receipt_root=Path(tmp),
            )
            assert len(receipt.tool_calls) == 2
            tc0 = receipt.tool_calls[0]
            assert tc0.tool_name == "get_historical_risk_metrics"
            assert tc0.evidence_refs == ["market_data.yfinance"]
            assert tc0.receipt_refs == ["r_abc123"]

    def test_agent_run_receipt_records_failed_tool_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_agent_run_receipt(
                goal="Read current IPS",
                profile_name="default",
                tool_calls=[
                    AgentToolCallSummary(
                        tool_name="get_current_ips_context",
                        side_effect="read",
                        ok=False,
                        error_code="STATECORE_UNAVAILABLE",
                        result_truncated=False,
                    ),
                ],
                outcome="partial",
                stop_reason="tool_unavailable",
                receipt_root=Path(tmp),
            )
            assert receipt.outcome == "partial"
            assert receipt.stop_reason == "tool_unavailable"
            tc = receipt.tool_calls[0]
            assert tc.ok is False
            assert tc.error_code == "STATECORE_UNAVAILABLE"

    def test_agent_run_receipt_is_not_execution_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_agent_run_receipt(
                goal="Draft a proposal",
                profile_name="review-draft",
                tool_calls=[],
                outcome="succeeded",
                stop_reason="goal_met",
                receipt_root=Path(tmp),
            )
            assert receipt.execution_allowed is False
            assert receipt.authority_transition is False
            file_path = Path(tmp) / "agent-runs" / f"{receipt.receipt_id}.json"
            payload = json.loads(file_path.read_text())
            assert payload["execution_allowed"] is False
            assert payload["authority_transition"] is False

    def test_agent_run_receipt_rejects_empty_goal(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:  # noqa: SIM117
            with pytest.raises(ValueError, match="non-blank goal"):
                write_agent_run_receipt(
                    goal="   ",
                    profile_name="default",
                    tool_calls=[],
                    outcome="succeeded",
                    stop_reason="done",
                    receipt_root=Path(tmp),
                )

    def test_agent_run_receipt_collects_artifact_and_context_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_agent_run_receipt(
                goal="Compare SPY vs QQQ allocation options",
                profile_name="review-draft",
                tool_calls=[],
                outcome="succeeded",
                stop_reason="goal_met",
                receipt_root=Path(tmp),
                context_refs=["capital_summary", "current_ips"],
                artifact_refs=["proposal_p_001", "review_note_rn_001"],
                evidence_refs=["market_data.yfinance"],
                data_gaps=["missing_VWAP_for_QQQ"],
            )
            assert "capital_summary" in receipt.context_refs
            assert "proposal_p_001" in receipt.artifact_refs
            assert "market_data.yfinance" in receipt.evidence_refs
            assert "missing_VWAP_for_QQQ" in receipt.data_gaps

    def test_agent_run_receipt_accepts_dict_tool_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_agent_run_receipt(
                goal="Test dict input",
                profile_name="default",
                tool_calls=[
                    {
                        "tool_name": "get_quote_snapshot",
                        "side_effect": "read",
                        "ok": True,
                    },
                ],
                outcome="succeeded",
                stop_reason="goal_met",
                receipt_root=Path(tmp),
            )
            assert receipt.tool_calls[0].tool_name == "get_quote_snapshot"

    def test_agent_run_receipt_strips_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_agent_run_receipt(
                goal="  Explain state  ",
                profile_name="default",
                tool_calls=[],
                outcome="succeeded",
                stop_reason="  done  ",
                receipt_root=Path(tmp),
            )
            assert receipt.goal == "Explain state"
            assert receipt.stop_reason == "done"

    def test_agent_run_receipt_model_is_frozen(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_agent_run_receipt(
                goal="Test frozen",
                profile_name="default",
                tool_calls=[],
                outcome="succeeded",
                stop_reason="done",
                receipt_root=Path(tmp),
            )
            with pytest.raises(ValidationError, match="frozen"):
                receipt.goal = "hijacked"  # type: ignore[misc]
