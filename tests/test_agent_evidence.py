from __future__ import annotations

import unittest
from dataclasses import replace
from unittest.mock import patch

from finharness.agent_evidence import (
    AGENT_EVIDENCE_PROVIDERS,
    build_agent_evidence_envelope,
    list_evidence_provider_metadata,
    resolve_evidence_providers,
)
from finharness.agent_runtime import agent_runtime_view, dispatch_agent_tool
from finharness.agent_tools import (
    AGENT_TOOL_ENTRIES,
    AgentToolAvailability,
    AgentToolEntry,
    get_quote_snapshot,
)


class AgentEvidenceTest(unittest.TestCase):
    def test_registry_metadata_is_non_authoritative(self) -> None:
        metadata = list_evidence_provider_metadata()

        self.assertEqual(
            [entry["provider_id"] for entry in metadata],
            sorted(AGENT_EVIDENCE_PROVIDERS),
        )
        for entry in metadata:
            self.assertFalse(entry["execution_allowed"])
            self.assertFalse(entry["authority_transition"])
            self.assertIn("availability", entry)
            self.assertIn("Not execution authorization.", entry["non_claims"])

    def test_tool_entries_reference_registered_evidence_providers(self) -> None:
        for entry in AGENT_TOOL_ENTRIES.values():
            with self.subTest(tool=entry.name):
                self.assertTrue(entry.evidence_provider_ids)
                providers = resolve_evidence_providers(entry.evidence_provider_ids)
                self.assertEqual(
                    [provider.provider_id for provider in providers],
                    list(entry.evidence_provider_ids),
                )
                metadata = entry.metadata()
                self.assertEqual(
                    metadata["evidence_provider_ids"],
                    list(entry.evidence_provider_ids),
                )

    def test_tool_entry_rejects_unknown_evidence_provider(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown agent evidence providers"):
            AgentToolEntry(
                name=get_quote_snapshot.name,
                tool=get_quote_snapshot,
                capability=AGENT_TOOL_ENTRIES[get_quote_snapshot.name].capability,
                toolset="market_data",
                description="Bad evidence provider declaration.",
                side_effect="read",
                check_fn=lambda: AgentToolAvailability(True),
                dispatch_handler=lambda _arguments: {},
                evidence_provider_ids=("missing.provider",),
            )

    def test_runtime_view_exposes_tool_evidence_providers(self) -> None:
        view = agent_runtime_view("default")
        quote = next(
            item
            for item in view["resolved_tools"]
            if item["name"] == "get_quote_snapshot"
        )

        self.assertEqual(quote["evidence_provider_ids"], ["market_data.yfinance"])
        self.assertEqual(
            [provider["provider_id"] for provider in quote["evidence_providers"]],
            ["market_data.yfinance"],
        )
        self.assertFalse(quote["evidence_providers"][0]["execution_allowed"])

    def test_build_envelope_collects_source_receipt_and_context_refs(self) -> None:
        envelope = build_agent_evidence_envelope(
            provider_ids=("capital_context.state_core",),
            result={
                "name": "capital_summary",
                "source_refs": ["statecore://position/1", "statecore://position/1"],
                "receipt_ref": "receipt://capital-summary",
                "context_pack_refs": ["context_pack://explicit"],
                "data_gaps": ["holdings truncated"],
                "non_claims": ["Context is review evidence only."],
            },
        ).model()

        self.assertEqual(envelope["provider_ids"], ["capital_context.state_core"])
        self.assertEqual(envelope["source_refs"], ["statecore://position/1"])
        self.assertEqual(envelope["receipt_refs"], ["receipt://capital-summary"])
        self.assertEqual(
            envelope["context_pack_refs"],
            ["context_pack://explicit", "context_pack://capital_summary"],
        )
        self.assertIn("holdings truncated", envelope["data_gaps"])
        self.assertFalse(envelope["execution_allowed"])

    def test_dispatch_success_attaches_evidence_envelope(self) -> None:
        original = AGENT_TOOL_ENTRIES["get_quote_snapshot"]
        patched = replace(
            original,
            dispatch_handler=lambda _arguments: {
                "symbol": "SPY",
                "source_refs": ["market_data://yfinance/quote/SPY"],
                "non_claims": ["Quote evidence only."],
            },
        )

        with patch.dict(AGENT_TOOL_ENTRIES, {"get_quote_snapshot": patched}):
            result = dispatch_agent_tool(
                profile_name="default",
                tool_name="get_quote_snapshot",
                arguments={"symbol": "SPY"},
            ).model()

        self.assertTrue(result["ok"])
        self.assertEqual(result["evidence"]["provider_ids"], ["market_data.yfinance"])
        self.assertEqual(
            result["evidence"]["source_refs"],
            ["market_data://yfinance/quote/SPY"],
        )
        self.assertFalse(result["evidence"]["authority_transition"])

    def test_result_budget_keeps_evidence_envelope(self) -> None:
        original = AGENT_TOOL_ENTRIES["get_quote_snapshot"]
        patched = replace(
            original,
            dispatch_handler=lambda _arguments: {
                "payload": "x" * 200,
                "source_refs": ["market_data://yfinance/quote/SPY"],
            },
            max_result_chars=60,
        )

        with patch.dict(AGENT_TOOL_ENTRIES, {"get_quote_snapshot": patched}):
            result = dispatch_agent_tool(
                profile_name="default",
                tool_name="get_quote_snapshot",
                arguments={"symbol": "SPY"},
            ).model()

        self.assertTrue(result["ok"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["error"]["code"], "RESULT_TOO_LARGE")
        self.assertEqual(
            result["evidence"]["source_refs"],
            ["market_data://yfinance/quote/SPY"],
        )


if __name__ == "__main__":
    unittest.main()
