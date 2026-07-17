from __future__ import annotations

import unittest
from decimal import Decimal

from finharness.agent_context import (
    CONTEXT_PACK_SPECS,
    AgentContextPackSpec,
    build_current_ips_context,
    build_ips_check_context,
    build_open_proposals_context,
    build_proposal_timeline_context,
)
from finharness.ips import record_ips
from finharness.statecore.models import Account, CashflowEvent, Position, Snapshot
from finharness.statecore.proposals import (
    create_governed_proposal,
    create_governed_review_event,
)
from finharness.statecore.store import write_records
from tests._scaffold import VALID_SCAFFOLD
from tests._statecore_fixtures import StateCoreFixture


class AgentContextPackTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = StateCoreFixture()
        self.engine = self.fixture.engine
        self.receipt_root = self.fixture.receipt_root
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
                position_id="spy",
                snapshot_id="s",
                account_id="brk",
                symbol="SPY",
                quantity=Decimal("1"),
                market_value=Decimal("8000"),
                source_refs=["position://spy"],
            ),
            Position(
                position_id="aapl",
                snapshot_id="s",
                account_id="brk",
                symbol="AAPL",
                quantity=Decimal("1"),
                market_value=Decimal("2000"),
            ),
            Position(
                position_id="cash",
                snapshot_id="s",
                account_id="brk",
                symbol="USD",
                quantity=Decimal("5000"),
                market_value=Decimal("5000"),
            ),
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
            ),
            CashflowEvent(
                cashflow_id="rent",
                description="Rent",
                amount=Decimal("-2000"),
                currency="USD",
                event_date="2026-07-01",
                category="expense",
                frequency="monthly",
            ),
        ]
        write_records([account, snapshot, *positions, *cashflows], engine=self.engine)

    def _create_proposal(self, proposal_id: str, *, claim: str | None = None) -> None:
        create_governed_proposal(
            kind="concentration_high",
            claim=claim or f"Review concentration for {proposal_id}.",
            evidence={"top_holding_weight": 0.8},
            decision_scaffold=VALID_SCAFFOLD,
            source_refs=[f"evidence://{proposal_id}"],
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id=proposal_id,
        )

    def assert_non_authoritative(self, payload: dict[str, object]) -> None:
        self.assertFalse(payload["execution_allowed"])
        self.assertIn("Not execution authorization.", payload["non_claims"])

    def test_current_ips_context_returns_data_gap_when_absent(self) -> None:
        pack = build_current_ips_context(self.engine)

        body = pack.model_dump(mode="json")
        self.assertFalse(body["available"])
        self.assertEqual(body["summary"], {})
        self.assertIn("No active IPS has been recorded.", body["data_gaps"])
        self.assert_non_authoritative(body)

    def test_current_ips_context_summarizes_active_policy(self) -> None:
        ips = record_ips(
            liquidity_floor_months=6,
            max_single_holding_pct="0.40",
            allowed_asset_classes=["public_equity"],
            restricted_actions=["no_margin"],
            source_refs=["policy://seed"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

        pack = build_current_ips_context(self.engine)
        body = pack.model_dump(mode="json")

        self.assertTrue(body["available"])
        self.assertEqual(body["summary"]["ips_id"], ips.ips_id)
        self.assertEqual(body["summary"]["thresholds"]["liquidity_floor_months"], "6")
        self.assertIn("policy://seed", body["source_refs"])
        self.assert_non_authoritative(body)

    def test_ips_check_context_reports_policy_results(self) -> None:
        self._seed_portfolio()
        record_ips(
            liquidity_floor_months=6,
            max_single_holding_pct="0.40",
            source_refs=["policy://seed"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

        body = build_ips_check_context(self.engine).model_dump(mode="json")

        self.assertTrue(body["available"])
        self.assertIn("single_holding_cap", body["summary"]["violations"])
        self.assertIn("liquidity_floor", body["summary"]["violations"])
        self.assertIn("policy://seed", body["source_refs"])
        self.assert_non_authoritative(body)

    def test_open_proposals_context_clamps_and_includes_scaffold(self) -> None:
        self._create_proposal("p_one")
        self._create_proposal("p_two")

        body = build_open_proposals_context(self.engine, limit=1).model_dump(mode="json")

        self.assertTrue(body["available"])
        self.assertEqual(body["summary"]["open_count"], 2)
        self.assertEqual(body["summary"]["returned_count"], 1)
        self.assertIn("decision_scaffold", body["summary"]["items"][0])
        self.assertIn("open proposals truncated to 1 items", body["data_gaps"])
        self.assert_non_authoritative(body)

    def test_open_proposals_context_honors_max_chars_after_compaction(self) -> None:
        original = CONTEXT_PACK_SPECS["open_proposals"]
        CONTEXT_PACK_SPECS["open_proposals"] = AgentContextPackSpec(
            name=original.name,
            description=original.description,
            source=original.source,
            max_items=10,
            max_chars=500,
        )
        self.addCleanup(CONTEXT_PACK_SPECS.__setitem__, "open_proposals", original)
        self._create_proposal("p_long", claim="Review " + ("concentration " * 400))

        pack = build_open_proposals_context(self.engine, limit=2)
        encoded = pack.model_dump_json()

        self.assertLessEqual(len(encoded), CONTEXT_PACK_SPECS["open_proposals"].max_chars)
        self.assertEqual(pack.summary, {"compacted": True})
        self.assertTrue(
            any("compact marker" in gap or "compact markers" in gap for gap in pack.data_gaps)
        )
        self.assert_non_authoritative(pack.model_dump(mode="json"))

    def test_proposal_timeline_context_reads_review_events(self) -> None:
        self._create_proposal("p_timeline")
        expectation = self.fixture._version_expectation("p_timeline")
        create_governed_review_event(
            proposal_id="p_timeline",
            kind="annotation",
            attester="Jane Control",
            reason="Adding review context.",
            text="Monitor the counter-evidence before any human decision.",
            source_refs=["review://note"],
            expectation=expectation,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

        body = build_proposal_timeline_context(self.engine, "p_timeline").model_dump(
            mode="json"
        )

        self.assertTrue(body["available"])
        self.assertEqual(body["summary"]["entry_count"], 1)
        self.assertEqual(body["summary"]["entries"][0]["kind"], "annotation")
        self.assertIn("review://note", body["source_refs"])
        self.assert_non_authoritative(body)

    def test_proposal_timeline_context_returns_gap_for_missing_proposal(self) -> None:
        body = build_proposal_timeline_context(self.engine, "missing").model_dump(mode="json")

        self.assertFalse(body["available"])
        self.assertIn("Proposal not found: missing", body["data_gaps"])
        self.assert_non_authoritative(body)


if __name__ == "__main__":
    unittest.main()
