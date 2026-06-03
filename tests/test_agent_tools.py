from __future__ import annotations

import json
import unittest

from agents.tool_context import ToolContext

from finharness.agent_tools import (
    evaluate_latest_risk_note,
    finance_research_agent,
    get_historical_risk_metrics,
    get_quote_snapshot,
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

    async def test_historical_metrics_tool_invokes_without_model(self) -> None:
        output = await get_historical_risk_metrics.on_invoke_tool(
            ctx("get_historical_risk_metrics"),
            json.dumps({"symbol": "SPY", "start": "2025-01-01", "end": "2025-02-15"}),
        )
        self.assertEqual(output["symbol"], "SPY")
        self.assertGreater(output["rows"], 10)
        self.assertIn("not TradingView/TV", output["data_source"])

    async def test_promptfoo_eval_tool_invokes_without_model(self) -> None:
        output = await evaluate_latest_risk_note.on_invoke_tool(
            ctx("evaluate_latest_risk_note"),
            "{}",
        )
        self.assertTrue(output["ok"], output)
        self.assertIn("1 passed", output["stdout_tail"])


if __name__ == "__main__":
    unittest.main()
