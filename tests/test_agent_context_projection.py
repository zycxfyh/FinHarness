from __future__ import annotations

import json
import unittest
from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

from finharness.agent_context_projection import (
    CONTEXT_PROJECTION_PROFILES,
    AgentContextPackProjectionSpec,
    AgentContextProjectionProfile,
    build_capital_context_projection_payload,
    context_projection_view,
    get_context_projection_profile,
    project_context_pack_payload,
)
from finharness.agent_runtime import agent_runtime_view, dispatch_agent_tool
from finharness.agent_tools import AGENT_TOOL_ENTRIES, AgentToolAvailability
from finharness.statecore.models import Account, CashflowEvent, Position, Snapshot
from finharness.statecore.store import write_records
from tests._statecore_fixtures import StateCoreFixture


class AgentContextProjectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = StateCoreFixture()
        self.engine = self.fixture.engine
        self.addCleanup(self.fixture.cleanup)

    def _seed_portfolio(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s",
            kind="portfolio",
            as_of_utc="2026-06-20T00:00:00+00:00",
            source_refs=["snapshot://s"],
        )
        positions = [
            Position(
                position_id=f"pos_{index}",
                snapshot_id="s",
                account_id="brk",
                symbol=f"SYM{index}",
                quantity=Decimal("1"),
                market_value=Decimal(str(1000 + index)),
                source_refs=[f"position://{index}"],
            )
            for index in range(12)
        ]
        cashflows = [
            CashflowEvent(
                cashflow_id="salary",
                description="Salary",
                amount=Decimal("5000"),
                currency="USD",
                event_date="2026-07-15",
                category="income",
                frequency="monthly",
            )
        ]
        write_records([account, snapshot, *positions, *cashflows], engine=self.engine)

    def test_projection_profiles_are_role_budgeted(self) -> None:
        default = get_context_projection_profile("default")
        review = get_context_projection_profile("review-draft")

        self.assertLess(default.total_max_chars, review.total_max_chars)
        self.assertLess(
            default.spec_for("open_proposals").max_items,
            review.spec_for("open_proposals").max_items,
        )
        self.assertFalse(default.execution_allowed)
        self.assertFalse(review.authority_transition)

    def test_context_projection_view_is_reviewable(self) -> None:
        view = context_projection_view("review-draft")

        self.assertEqual(view["profile_name"], "review-draft")
        self.assertTrue(view["pack_specs"])
        self.assertFalse(view["execution_allowed"])

    def test_single_pack_projection_selects_role_specific_fields(self) -> None:
        payload = {
            "name": "capital_summary",
            "available": True,
            "summary": {
                "as_of_date": "2026-06-20",
                "net_worth": "1000",
                "top_holding": {"symbol": "SPY"},
                "holdings": [{"symbol": f"SYM{index}"} for index in range(20)],
                "internal_noise": "x" * 100,
            },
            "source_refs": [f"source://{index}" for index in range(20)],
            "data_gaps": [],
            "non_claims": ["Not execution authorization."],
            "execution_allowed": False,
        }

        projected = project_context_pack_payload(
            profile_name="default",
            tool_name="get_capital_summary_context",
            payload=payload,
        )

        self.assertEqual(projected["projection"]["profile_name"], "default")
        self.assertEqual(projected["context_pack_refs"], ["context_pack://capital_summary"])
        self.assertNotIn("holdings", projected["summary"])
        self.assertNotIn("internal_noise", projected["summary"])
        self.assertLessEqual(len(projected["source_refs"]), 10)
        self.assertTrue(
            any("omitted summary keys" in gap for gap in projected["data_gaps"])
        )
        self.assertFalse(projected["execution_allowed"])

    def test_projection_drops_unknown_top_level_fields(self) -> None:
        payload = {
            "name": "capital_summary",
            "available": True,
            "summary": {"as_of_date": "2026-06-20", "net_worth": "1000"},
            "source_refs": ["statecore://summary"],
            "raw_state_dump": "x" * 100_000,
            "private_notes": "do not pass through",
        }

        projected = project_context_pack_payload(
            profile_name="default",
            tool_name="get_capital_summary_context",
            payload=payload,
        )

        self.assertNotIn("raw_state_dump", projected)
        self.assertNotIn("private_notes", projected)
        self.assertIn("statecore://summary", projected["source_refs"])
        self.assertEqual(
            projected["projection"]["dropped_top_level_keys"],
            ["private_notes", "raw_state_dump"],
        )
        self.assertTrue(
            any("omitted top-level keys" in gap for gap in projected["data_gaps"])
        )
        self.assertLessEqual(
            len(json.dumps(projected, sort_keys=True, default=str)),
            get_context_projection_profile("default")
            .spec_for("capital_summary")
            .max_chars,
        )

    def test_marker_fallback_preserves_minimum_source_provenance(self) -> None:
        tiny_profile = AgentContextProjectionProfile(
            profile_name="default",
            total_max_chars=1_000,
            pack_specs=(
                AgentContextPackProjectionSpec(
                    pack_name="capital_summary",
                    priority=10,
                    max_chars=10,
                    max_items=1,
                    max_source_refs=3,
                    summary_keys=("net_worth",),
                ),
            ),
        )
        payload = {
            "name": "capital_summary",
            "available": True,
            "summary": {"net_worth": "x" * 10_000},
            "source_refs": ["statecore://summary", "statecore://position"],
        }

        with patch.dict(CONTEXT_PROJECTION_PROFILES, {"default": tiny_profile}):
            projected = project_context_pack_payload(
                profile_name="default",
                tool_name="get_capital_summary_context",
                payload=payload,
            )

        self.assertEqual(projected["summary"], {"compacted": True})
        self.assertEqual(projected["source_refs"], ["statecore://summary"])
        self.assertTrue(projected["projection"]["truncated"])
        self.assertEqual(projected["projection"]["original_source_ref_count"], 2)
        self.assertTrue(projected["projection"]["source_refs_truncated"])

    def test_build_capital_context_projection_payload_returns_office_brief(self) -> None:
        self._seed_portfolio()

        body = build_capital_context_projection_payload(
            profile_name="review-draft",
            open_proposals_limit=10,
            engine=self.engine,
        )

        self.assertEqual(body["name"], "capital_context_projection")
        self.assertEqual(body["profile_name"], "review-draft")
        self.assertGreaterEqual(len(body["packs"]), 3)
        self.assertIn("context_pack://capital_summary", body["context_pack_refs"])
        self.assertLessEqual(
            len(json.dumps(body, sort_keys=True, default=str)),
            get_context_projection_profile("review-draft").total_max_chars,
        )
        self.assertFalse(body["execution_allowed"])

    def test_blocked_admission_survives_default_and_review_projections(self) -> None:
        self._seed_portfolio()

        for profile_name in ("default", "review-draft"):
            with self.subTest(profile=profile_name):
                body = build_capital_context_projection_payload(
                    profile_name=profile_name,
                    engine=self.engine,
                )
                capital = next(
                    pack for pack in body["packs"] if pack["name"] == "capital_summary"
                )
                summary = capital["summary"]
                self.assertFalse(summary["asset_valuation_admitted"])
                self.assertFalse(summary["net_worth_admitted"])
                self.assertIsNone(summary["concentration_flagged"])
                self.assertTrue(summary["asset_valuation_blockers"])
                self.assertIn("per_currency_totals", summary)
                self.assertIn("liability_per_currency_totals", summary)

    def test_runtime_view_exposes_context_projection_policy(self) -> None:
        view = agent_runtime_view("review-draft")

        self.assertTrue(
            view["runtime_rules"]["context_projection_is_profile_budgeted"]
        )
        self.assertEqual(view["context_projection"]["profile_name"], "review-draft")

    def test_dispatch_projects_context_pack_result_before_budgeting(self) -> None:
        original = AGENT_TOOL_ENTRIES["get_capital_summary_context"]
        patched = replace(
            original,
            check_fn=lambda: AgentToolAvailability(True),
            dispatch_handler=lambda _arguments: {
                "name": "capital_summary",
                "available": True,
                "summary": {
                    "as_of_date": "2026-06-20",
                    "top_holding": {"symbol": "SPY"},
                    "holdings": [{"symbol": f"SYM{index}"} for index in range(20)],
                    "internal_noise": "x" * 100,
                },
                "source_refs": ["statecore://summary"],
                "data_gaps": [],
                "non_claims": ["Not execution authorization."],
                "execution_allowed": False,
            },
            max_result_chars=2_000,
        )

        with patch.dict(AGENT_TOOL_ENTRIES, {"get_capital_summary_context": patched}):
            result = dispatch_agent_tool(
                profile_name="default",
                tool_name="get_capital_summary_context",
                arguments={},
            ).model()

        self.assertTrue(result["ok"])
        self.assertIn("projection", result["result"])
        self.assertEqual(result["result"]["projection"]["profile_name"], "default")
        self.assertNotIn("holdings", result["result"]["summary"])
        self.assertEqual(result["evidence"]["context_pack_refs"], ["context_pack://capital_summary"])

    def test_context_projection_dispatch_rejects_profile_argument_bypass(self) -> None:
        original = AGENT_TOOL_ENTRIES["get_capital_context_projection"]
        patched = replace(
            original,
            check_fn=lambda: AgentToolAvailability(True),
            dispatch_handler=lambda _arguments: {
                "name": "capital_context_projection",
                "available": True,
            },
        )

        with patch.dict(AGENT_TOOL_ENTRIES, {"get_capital_context_projection": patched}):
            result = dispatch_agent_tool(
                profile_name="default",
                tool_name="get_capital_context_projection",
                arguments={"profile_name": "review-draft", "open_proposals_limit": 10},
            ).model()

        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "PROFILE_NOT_ALLOWED")

    def test_context_projection_dispatch_injects_active_profile(self) -> None:
        original = AGENT_TOOL_ENTRIES["get_capital_context_projection"]
        patched = replace(
            original,
            check_fn=lambda: AgentToolAvailability(True),
            dispatch_handler=lambda arguments: {
                "name": "capital_context_projection",
                "available": True,
                "profile_name": arguments["profile_name"],
                "packs": [],
                "source_refs": [],
                "context_pack_refs": [],
                "data_gaps": [],
                "non_claims": [],
                "execution_allowed": False,
            },
        )

        with patch.dict(AGENT_TOOL_ENTRIES, {"get_capital_context_projection": patched}):
            result = dispatch_agent_tool(
                profile_name="review-draft",
                tool_name="get_capital_context_projection",
                arguments={"open_proposals_limit": 10},
            ).model()

        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["profile_name"], "review-draft")


if __name__ == "__main__":
    unittest.main()
