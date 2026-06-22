from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

import pandas as pd
from agents.tool_context import ToolContext

from finharness.agent_tools import (
    evaluate_latest_risk_note_payload,
    finance_research_agent,
    get_historical_risk_metrics,
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
            ],
        )
        self.assertEqual(len(finance_research_agent.tools), 3)

    def test_tool_schemas_are_strict(self) -> None:
        self.assertFalse(get_quote_snapshot.params_json_schema["additionalProperties"])
        self.assertEqual(
            set(get_historical_risk_metrics.params_json_schema["required"]),
            {"symbol", "start", "end"},
        )

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
