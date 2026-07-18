from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from finharness.daily_brief import (
    DO_NOTHING_LINE,
    MARKET_CONTEXT_OFFLINE_PLACEHOLDER,
    SLOT_TITLES,
    compute_daily_brief,
    record_daily_brief,
)
from finharness.statecore.models import (
    Account,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
)
from finharness.statecore.store import init_state_core, read_all, write_records


class DailyBriefTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _seed(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snap1 = Snapshot(
            snapshot_id="snap1", kind="portfolio", as_of_utc="2026-06-18T00:00:00+00:00"
        )
        snap2 = Snapshot(
            snapshot_id="snap2", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        positions = [
            Position(
                position_id="p1_spy",
                snapshot_id="snap1",
                account_id="brk",
                symbol="SPY",
                quantity=Decimal("10"),
                market_value=Decimal("1000"),
                valuation_currency="USD",
                unit_price=Decimal("100"),
                price_currency="USD",
                valued_at_utc="2026-06-18T00:00:00+00:00",
                price_source_ref="fixture:prices",
                valuation_status="valued",
            ),
            Position(
                position_id="p2_spy",
                snapshot_id="snap2",
                account_id="brk",
                symbol="SPY",
                quantity=Decimal("15"),
                market_value=Decimal("1500"),
                valuation_currency="USD",
                unit_price=Decimal("100"),
                price_currency="USD",
                valued_at_utc="2026-06-19T00:00:00+00:00",
                price_source_ref="fixture:prices",
                valuation_status="valued",
            ),
            Position(
                position_id="p2_aapl",
                snapshot_id="snap2",
                account_id="brk",
                symbol="AAPL",
                quantity=Decimal("5"),
                market_value=Decimal("500"),
                valuation_currency="USD",
                unit_price=Decimal("100"),
                price_currency="USD",
                valued_at_utc="2026-06-19T00:00:00+00:00",
                price_source_ref="fixture:prices",
                valuation_status="valued",
            ),
        ]
        proposal = Proposal(
            proposal_id="prop1", kind="rebalance_review", claim="Review concentration"
        )
        write_records([account, snap1, snap2, *positions, proposal], engine=self.engine)

    def test_compute_daily_brief_assembles_sections_and_change(self) -> None:
        self._seed()

        brief = compute_daily_brief(self.engine, as_of_date=date(2026, 6, 20))

        self.assertFalse(brief.execution_allowed)
        self.assertTrue(brief.headline)
        self.assertEqual(brief.open_review_count, 1)
        # Two portfolio snapshots -> a holdings change is computed (1000 -> 2000).
        self.assertEqual(brief.holdings_change, 1000.0)
        self.assertEqual(brief.net_worth, 2000.0)
        # P3 v1: exactly the ten fixed slots, in the fixed order.
        titles = [section.title for section in brief.sections]
        self.assertEqual(list(titles), list(SLOT_TITLES))

    def test_ten_slots_fixed_and_never_empty(self) -> None:
        """Gate conditions 1, 2, 7: ten slots, order fixed, no slot ever disappears."""
        self._seed()

        brief = compute_daily_brief(self.engine, as_of_date=date(2026, 6, 20))

        self.assertEqual(len(brief.sections), 10)
        self.assertEqual(tuple(s.title for s in brief.sections), SLOT_TITLES)
        for section in brief.sections:
            self.assertTrue(section.lines, f"slot {section.title!r} must not be empty")
        slots = {s.title: s.lines for s in brief.sections}
        # Do-nothing (slot 8) is always present.
        self.assertEqual(slots["Do-nothing option"], (DO_NOTHING_LINE,))
        # Market context (slot 6) is the offline placeholder in v1 — no live data, no network.
        self.assertEqual(slots["Market context"], (MARKET_CONTEXT_OFFLINE_PLACEHOLDER,))
        # Candidate decisions read from governed proposals (seed has one).
        candidates = slots["Candidate decisions"]
        self.assertTrue(any("Review concentration" in line for line in candidates))

    def test_empty_state_still_emits_all_ten_slots(self) -> None:
        """Gate condition 2: with no data, slots use explicit placeholders, none vanish."""
        brief = compute_daily_brief(self.engine, as_of_date=date(2026, 6, 20))

        self.assertEqual(tuple(s.title for s in brief.sections), SLOT_TITLES)
        for section in brief.sections:
            self.assertTrue(section.lines, f"slot {section.title!r} must not be empty")

    def test_empty_state_emits_no_false_reassurance(self) -> None:
        """Gate condition 2 (semantic): absence of data must not read as 'safe'."""
        brief = compute_daily_brief(self.engine, as_of_date=date(2026, 6, 20))
        slots = {s.title: " ".join(s.lines) for s in brief.sections}

        # Cash: unverified total must not render as a concrete 0.00.
        self.assertNotIn("Cash on record 0.00", slots["Cash & liquidity status"])
        self.assertIn("not verified", slots["Cash & liquidity status"])
        # Concentration: no holdings is "cannot assess", not "within threshold".
        self.assertNotIn("within the", slots["Concentration risks"])
        self.assertIn("cannot be unified/valued", slots["Concentration risks"])
        # Do-nothing: must not claim inaction carries "no new risk" outright.
        self.assertIn("existing exposures", slots["Do-nothing option"])
        self.assertNotIn("no transaction cost or new risk", slots["Do-nothing option"])

    def test_preserves_prior_section_data(self) -> None:
        """Gate condition 3: original four-section data is preserved across the restructure."""
        self._seed()

        brief = compute_daily_brief(self.engine, as_of_date=date(2026, 6, 20))
        slots = {s.title: " ".join(s.lines) for s in brief.sections}

        # net_worth preserved (top-level field + slot 1).
        self.assertEqual(brief.net_worth, 2000.0)
        self.assertIn("Net worth", slots["Net worth snapshot"])
        # concentration preserved (slot 4).
        self.assertTrue(slots["Concentration risks"])
        # obligations preserved (folded into slot 2).
        self.assertTrue(slots["Cash & liquidity status"])
        # open_review_count preserved (top-level field + slot 10).
        self.assertEqual(brief.open_review_count, 1)
        self.assertIn("1 open proposal", slots["Review prompts"])
        # source_refs / data_gaps remain top-level fields.
        self.assertIsInstance(brief.source_refs, tuple)
        self.assertIsInstance(brief.data_gaps, tuple)

    def test_blocked_valuation_never_renders_unified_capital_numbers(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="mixed", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        positions = [
            Position(
                position_id="usd",
                snapshot_id="mixed",
                account_id="brk",
                symbol="SPY",
                quantity=Decimal("1"),
                market_value=Decimal("100"),
                valuation_currency="USD",
                unit_price=Decimal("100"),
                price_currency="USD",
                valued_at_utc="2026-06-19T00:00:00+00:00",
                price_source_ref="fixture:prices",
                valuation_status="valued",
            ),
            Position(
                position_id="jpy",
                snapshot_id="mixed",
                account_id="brk",
                symbol="7203",
                quantity=Decimal("1"),
                market_value=Decimal("20000"),
                valuation_currency="JPY",
                unit_price=Decimal("20000"),
                price_currency="JPY",
                valued_at_utc="2026-06-19T00:00:00+00:00",
                price_source_ref="fixture:prices",
                valuation_status="valued",
            ),
        ]
        write_records([account, snapshot, *positions], engine=self.engine)

        brief = compute_daily_brief(self.engine, as_of_date=date(2026, 6, 20))
        slots = {section.title: " ".join(section.lines) for section in brief.sections}

        self.assertIsNone(brief.net_worth)
        self.assertIn("cannot be unified/valued", brief.headline)
        self.assertIn("Admitted position total USD: 100.00 USD", slots["Net worth snapshot"])
        self.assertIn(
            "Admitted position total JPY: 20,000.00 JPY",
            slots["Net worth snapshot"],
        )
        self.assertNotIn("Net worth 20,100", slots["Net worth snapshot"])
        self.assertIn("cannot be unified/valued", slots["Concentration risks"])

    def test_record_daily_brief_writes_a_dated_receipt(self) -> None:
        self._seed()
        receipt_root = self.root / "receipts" / "daily-brief"

        brief, _receipt_ref = record_daily_brief(
            self.engine, receipt_root=receipt_root, as_of_date=date(2026, 6, 20)
        )

        receipt_path = receipt_root / f"receipt_daily_brief_{brief.as_of_date}.json"
        self.assertTrue(receipt_path.exists())
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "daily_brief")
        self.assertFalse(payload["execution_allowed"])
        receipts = read_all(ReceiptIndex, engine=self.engine)
        self.assertEqual(receipts[0].kind, "daily_brief")


if __name__ == "__main__":
    unittest.main()
