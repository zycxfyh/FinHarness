from __future__ import annotations

import json
import subprocess
import unittest
from unittest.mock import patch

import pandas as pd
from agents.tool_context import ToolContext

from finharness.agent_capabilities import list_agent_profiles, tool_names_for_profile
from finharness.agent_runtime import resolve_agent_tool_entries
from finharness.agent_tools import (
    AGENT_TOOL_ENTRIES,
    AGENT_TOOL_REGISTRY,
    AgentToolAvailability,
    AgentToolEntry,
    agent_tool_entries_for_profile,
    agent_tool_metadata_for_profile,
    agent_tools_for_profile,
    build_finance_research_agent,
    current_ips_context_payload,
    describe_agent,
    draft_governed_proposal_from_context,
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
        self.assertEqual(tool_names(), list(tool_names_for_profile("default")))
        self.assertNotIn("draft_governed_proposal_from_context", tool_names())
        self.assertIn(
            "draft_governed_proposal_from_context",
            tool_names("review-draft"),
        )

    def test_tool_registry_covers_every_profile_tool_name(self) -> None:
        for profile in list_agent_profiles():
            with self.subTest(profile=profile.name):
                self.assertEqual(
                    [entry.name for entry in agent_tool_entries_for_profile(profile.name)],
                    list(tool_names_for_profile(profile.name)),
                )

    def test_build_agent_uses_exact_profile_toolset(self) -> None:
        default_agent = build_finance_research_agent()
        review_agent = build_finance_research_agent("review-draft")

        self.assertEqual(
            [tool.name for tool in default_agent.tools],
            list(tool_names_for_profile("default")),
        )
        self.assertNotIn(
            "draft_governed_proposal_from_context",
            {tool.name for tool in default_agent.tools},
        )
        self.assertEqual(
            [tool.name for tool in review_agent.tools],
            [
                item.entry.name
                for item in resolve_agent_tool_entries("review-draft")
                if item.model_visible
            ],
        )

    def test_profile_runtime_fail_closed_for_unknown_or_unregistered_tools(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown agent capability profile"):
            agent_tools_for_profile("missing")

        with (
            patch.dict(AGENT_TOOL_ENTRIES, {}, clear=True),
            self.assertRaisesRegex(ValueError, "unregistered tools"),
        ):
            agent_tools_for_profile("default")

    def test_describe_agent_uses_profile_runtime_tools(self) -> None:
        output = json.loads(describe_agent("review-draft"))

        self.assertEqual(output["profile"]["name"], "review-draft")
        resolved_names = [
            entry["name"]
            for entry in output["resolved_tools"]
            if entry["model_visible"]
        ]
        self.assertEqual(output["tools"], resolved_names)
        self.assertEqual(
            [entry["name"] for entry in output["tool_entries"]],
            list(tool_names_for_profile("review-draft")),
        )
        draft_entry = next(
            entry
            for entry in output["tool_entries"]
            if entry["name"] == "draft_governed_proposal_from_context"
        )
        self.assertEqual(draft_entry["capability"], "capital-propose")
        self.assertEqual(draft_entry["toolset"], "proposal_draft")
        self.assertEqual(draft_entry["side_effect"], "append_only_review_write")
        self.assertTrue(draft_entry["requires_human_review"])
        self.assertFalse(draft_entry["execution_allowed"])
        self.assertFalse(draft_entry["authority_transition"])

    def test_agent_tool_entries_are_profile_ordered_and_non_authoritative(self) -> None:
        self.assertEqual(set(AGENT_TOOL_REGISTRY), set(AGENT_TOOL_ENTRIES))
        for profile in list_agent_profiles():
            with self.subTest(profile=profile.name):
                entries = agent_tool_entries_for_profile(profile.name)
                self.assertEqual(
                    [entry.name for entry in entries],
                    list(tool_names_for_profile(profile.name)),
                )
                for entry in entries:
                    self.assertFalse(entry.execution_allowed)
                    self.assertFalse(entry.authority_transition)
                    self.assertTrue(entry.description)
                    self.assertIn(entry.capability, profile.capabilities)
                    self.assertIn("Not execution authorization.", entry.non_claims)
                    availability = entry.check_fn()
                    self.assertIsInstance(availability, AgentToolAvailability)

    def test_default_profile_tool_metadata_has_no_append_only_write_surface(self) -> None:
        metadata = agent_tool_metadata_for_profile("default")

        self.assertEqual([entry["name"] for entry in metadata], tool_names())
        self.assertNotIn(
            "append_only_review_write",
            {entry["side_effect"] for entry in metadata},
        )
        for entry in metadata:
            self.assertFalse(entry["requires_human_review"])
            self.assertFalse(entry["execution_allowed"])
            self.assertFalse(entry["authority_transition"])
            self.assertIn("availability", entry)

    def test_tool_entry_constructor_rejects_authority_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "name mismatch"):
            AgentToolEntry(
                name="wrong",
                tool=get_quote_snapshot,
                capability=AGENT_TOOL_ENTRIES[get_quote_snapshot.name].capability,
                toolset="market_data",
                description="Bad entry.",
                side_effect="read",
                check_fn=lambda: AgentToolAvailability(True),
                dispatch_handler=lambda _arguments: {},
            )

        with self.assertRaisesRegex(ValueError, "execution authority"):
            AgentToolEntry(
                name=get_quote_snapshot.name,
                tool=get_quote_snapshot,
                capability=AGENT_TOOL_ENTRIES[get_quote_snapshot.name].capability,
                toolset="market_data",
                description="Bad entry.",
                side_effect="read",
                check_fn=lambda: AgentToolAvailability(True),
                dispatch_handler=lambda _arguments: {},
                execution_allowed=True,
            )

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

    def test_proposal_draft_tool_schema_has_fixed_top_level_fields(self) -> None:
        schema = draft_governed_proposal_from_context.params_json_schema
        self.assertEqual(
            set(schema["properties"]),
            {
                "kind",
                "claim",
                "evidence",
                "decision_scaffold",
                "source_refs",
                "reason",
                "assumptions",
                "limitations",
                "context_pack_refs",
                "profile_name",
            },
        )
        self.assertEqual(
            set(schema["required"]),
            {
                "kind",
                "claim",
                "evidence",
                "decision_scaffold",
                "source_refs",
                "reason",
            },
        )
        self.assertNotIn("additionalProperties", schema)
        self.assertTrue(schema["properties"]["evidence"]["additionalProperties"])
        self.assertTrue(schema["properties"]["decision_scaffold"]["additionalProperties"])

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
