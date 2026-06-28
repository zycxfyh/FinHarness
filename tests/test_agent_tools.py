from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

import pandas as pd
from agents.tool_context import ToolContext

from finharness.agent_tools import (
    current_ips_context_payload,
    evaluate_latest_risk_note_payload,
    finance_research_agent,
    get_capital_summary_context,
    get_current_ips_context,
    get_historical_risk_metrics,
    get_ips_check_context,
    get_open_proposals_context,
    get_proposal_timeline_context,
    get_quote_snapshot,
    historical_risk_metrics_payload,
    tool_names,
)


def ctx(tool_name: str, arguments: str = "") -> ToolContext[None]:
    return ToolContext(
        context=None,
        tool_name=tool_name,
        tool_call_id="test",
        tool_arguments=arguments,
    )


class AgentToolsTest(unittest.IsolatedAsyncioTestCase):
    def test_agent_registers_expected_tools(self) -> None:
        self.assertEqual(
            tool_names(),
            [
                "get_quote_snapshot",
                "get_historical_risk_metrics",
                "evaluate_latest_risk_note",
                "get_capital_summary_context",
                "get_current_ips_context",
                "get_ips_check_context",
                "get_open_proposals_context",
                "get_proposal_timeline_context",
            ],
        )
        self.assertEqual(len(finance_research_agent.tools), 8)

    def test_agent_does_not_expose_mutating_capital_tools(self) -> None:
        names = set(tool_names())
        forbidden = {
            "create_governed_proposal",
            "revise_governed_proposal_scaffold",
            "create_governed_attestation",
            "create_governed_review_event",
            "create_action_intent",
            "approve_proposal",
            "reject_proposal",
            "execute_order",
            "transfer_funds",
        }
        self.assertTrue(forbidden.isdisjoint(names))

    def test_tool_schemas_are_strict(self) -> None:
        self.assertFalse(get_quote_snapshot.params_json_schema["additionalProperties"])
        self.assertEqual(
            set(get_historical_risk_metrics.params_json_schema["required"]),
            {"symbol", "start", "end"},
        )

    def test_context_tool_schemas_are_strict(self) -> None:
        context_tools = [
            get_capital_summary_context,
            get_current_ips_context,
            get_ips_check_context,
            get_open_proposals_context,
            get_proposal_timeline_context,
        ]
        for tool in context_tools:
            with self.subTest(tool=tool.name):
                schema = tool.params_json_schema
                self.assertFalse(schema["additionalProperties"])

        open_schema = get_open_proposals_context.params_json_schema
        self.assertEqual(set(open_schema["properties"]), {"limit"})

        timeline_schema = get_proposal_timeline_context.params_json_schema
        self.assertEqual(set(timeline_schema["properties"]), {"proposal_id", "limit"})
        self.assertEqual(set(timeline_schema["required"]), {"proposal_id", "limit"})

    def test_context_payload_unavailable_state_core_is_non_authoritative(self) -> None:
        from finharness.statecore.store import StateCoreStoreError

        with patch("finharness.agent_tools.open_state_core") as open_state_core:
            open_state_core.side_effect = StateCoreStoreError("state-core missing")
            output = current_ips_context_payload()
        self.assertFalse(output["available"])
        self.assertFalse(output["execution_allowed"])
        self.assertIn("state-core missing", output["data_gaps"])

    def test_historical_metrics_payload_invokes_without_model(self) -> None:
        history = pd.DataFrame(
            {
                "date": pd.date_range("2025-01-01", periods=20),
                "open": [100.0 + index for index in range(20)],
                "high": [101.0 + index for index in range(20)],
                "low": [99.0 + index for index in range(20)],
                "close": [100.0 + index for index in range(20)],
                "volume": [1_000_000 + index for index in range(20)],
            }
        )
        with patch("finharness.agent_tools.fetch_yfinance_history", return_value=history):
            output = historical_risk_metrics_payload(
                symbol="SPY",
                start="2025-01-01",
                end="2025-02-15",
            )
        self.assertEqual(output["symbol"], "SPY")
        self.assertGreater(output["rows"], 10)
        self.assertIn("not TradingView/TV", output["data_source"])

    def test_promptfoo_eval_payload_invokes_bounded_subprocess(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["promptfoo"],
            returncode=0,
            stdout="1 passed\n",
            stderr="",
        )
        with patch("finharness.agent_tools.subprocess.run", return_value=completed) as run:
            output = evaluate_latest_risk_note_payload()
        self.assertTrue(output["ok"], output)
        self.assertIn("1 passed", output["stdout_tail"])
        self.assertEqual(run.call_args.kwargs["timeout"], 60.0)


if __name__ == "__main__":
    unittest.main()
