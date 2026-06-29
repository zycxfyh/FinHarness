from __future__ import annotations

import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from finharness.agent_runtime import (
    agent_runtime_view,
    dispatch_agent_tool,
    resolve_agent_tool_entries,
)
from finharness.agent_tools import (
    AGENT_TOOL_ENTRIES,
    AgentToolAvailability,
    build_finance_research_agent,
    describe_agent,
    get_quote_snapshot,
)


class AgentRuntimeTest(unittest.TestCase):
    def test_resolver_projects_default_visible_tools_without_draft(self) -> None:
        resolved = resolve_agent_tool_entries("default")

        visible_names = [item.entry.name for item in resolved if item.model_visible]
        self.assertIn("get_capital_summary_context", visible_names)
        self.assertNotIn("draft_governed_proposal_from_context", visible_names)
        self.assertTrue(
            all(item.entry.unavailable_policy != "fail_closed" for item in resolved)
        )
        self.assertTrue(all(not item.entry.execution_allowed for item in resolved))

    def test_describe_agent_exposes_runtime_view(self) -> None:
        body = json.loads(describe_agent("review-draft"))

        self.assertIn("resolved_tools", body)
        self.assertIn("hidden_tools", body)
        self.assertIn("unavailable_tools", body)
        self.assertTrue(body["runtime_rules"]["availability_affects_model_visibility"])
        draft = next(
            item
            for item in body["resolved_tools"] + body["hidden_tools"]
            if item["name"] == "draft_governed_proposal_from_context"
        )
        self.assertEqual(draft["side_effect"], "append_only_review_write")
        self.assertFalse(draft["execution_allowed"])

    def test_unavailable_fail_closed_tool_is_hidden_from_agent(self) -> None:
        original = AGENT_TOOL_ENTRIES["draft_governed_proposal_from_context"]
        unavailable = replace(
            original,
            check_fn=lambda: AgentToolAvailability(False, "state-core missing"),
        )

        with patch.dict(
            AGENT_TOOL_ENTRIES,
            {"draft_governed_proposal_from_context": unavailable},
        ):
            view = agent_runtime_view("review-draft")
            agent = build_finance_research_agent("review-draft")

        self.assertIn(
            "draft_governed_proposal_from_context",
            {item["name"] for item in view["hidden_tools"]},
        )
        self.assertIn(
            "draft_governed_proposal_from_context",
            {item["name"] for item in view["unavailable_tools"]},
        )
        self.assertNotIn(
            "draft_governed_proposal_from_context",
            {tool.name for tool in agent.tools},
        )

    def test_unavailable_diagnostic_stub_remains_visible(self) -> None:
        original = AGENT_TOOL_ENTRIES["get_capital_summary_context"]
        unavailable = replace(
            original,
            check_fn=lambda: AgentToolAvailability(False, "state-core missing"),
        )

        with patch.dict(AGENT_TOOL_ENTRIES, {"get_capital_summary_context": unavailable}):
            view = agent_runtime_view("default")

        diagnostic = next(
            item
            for item in view["resolved_tools"]
            if item["name"] == "get_capital_summary_context"
        )
        self.assertTrue(diagnostic["degraded"])
        self.assertFalse(diagnostic["availability"]["available"])

    def test_dispatch_rejects_unregistered_and_profile_disallowed_tools(self) -> None:
        missing = dispatch_agent_tool(
            profile_name="default",
            tool_name="not_a_tool",
            arguments={},
        ).model()
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"]["code"], "TOOL_UNREGISTERED")
        self.assertFalse(missing["execution_allowed"])

        disallowed = dispatch_agent_tool(
            profile_name="default",
            tool_name="draft_governed_proposal_from_context",
            arguments={},
        ).model()
        self.assertFalse(disallowed["ok"])
        self.assertEqual(disallowed["error"]["code"], "PROFILE_NOT_ALLOWED")
        self.assertFalse(disallowed["authority_transition"])

    def test_dispatch_checks_availability_and_required_arguments(self) -> None:
        original = AGENT_TOOL_ENTRIES["draft_governed_proposal_from_context"]
        unavailable = replace(
            original,
            check_fn=lambda: AgentToolAvailability(False, "state-core missing"),
        )
        with patch.dict(
            AGENT_TOOL_ENTRIES,
            {"draft_governed_proposal_from_context": unavailable},
        ):
            blocked = dispatch_agent_tool(
                profile_name="review-draft",
                tool_name="draft_governed_proposal_from_context",
                arguments={},
            ).model()
        self.assertFalse(blocked["ok"])
        self.assertEqual(blocked["error"]["code"], "TOOL_UNAVAILABLE")
        self.assertFalse(blocked["error"]["recoverable"])

        missing_arg = dispatch_agent_tool(
            profile_name="default",
            tool_name="get_quote_snapshot",
            arguments={},
        ).model()
        self.assertFalse(missing_arg["ok"])
        self.assertEqual(missing_arg["error"]["code"], "SCHEMA_VALIDATION_FAILED")

    def test_dispatch_success_and_result_budget(self) -> None:
        original = AGENT_TOOL_ENTRIES["get_quote_snapshot"]
        ok_entry = replace(
            original,
            dispatch_handler=lambda _arguments: {"symbol": "SPY", "price": 500},
        )
        large_entry = replace(
            original,
            dispatch_handler=lambda _arguments: {"payload": "x" * 200},
            max_result_chars=60,
        )

        with patch.dict(AGENT_TOOL_ENTRIES, {"get_quote_snapshot": ok_entry}):
            ok = dispatch_agent_tool(
                profile_name="default",
                tool_name="get_quote_snapshot",
                arguments={"symbol": "SPY"},
            ).model()
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["result"]["symbol"], "SPY")
        self.assertFalse(ok["execution_allowed"])

        with patch.dict(AGENT_TOOL_ENTRIES, {"get_quote_snapshot": large_entry}):
            large = dispatch_agent_tool(
                profile_name="default",
                tool_name="get_quote_snapshot",
                arguments={"symbol": "SPY"},
            ).model()
        self.assertTrue(large["ok"])
        self.assertTrue(large["truncated"])
        self.assertEqual(large["error"]["code"], "RESULT_TOO_LARGE")
        self.assertFalse(large["authority_transition"])

    def test_tool_entry_metadata_includes_runtime_policy(self) -> None:
        entry = AGENT_TOOL_ENTRIES[get_quote_snapshot.name].metadata()

        self.assertIn("unavailable_policy", entry)
        self.assertIn("max_result_chars", entry)
        self.assertFalse(entry["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
