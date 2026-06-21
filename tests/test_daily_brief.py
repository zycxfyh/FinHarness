from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from finharness.daily_brief import compute_daily_brief, record_daily_brief
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
            ),
            Position(
                position_id="p2_spy",
                snapshot_id="snap2",
                account_id="brk",
                symbol="SPY",
                quantity=Decimal("15"),
                market_value=Decimal("1500"),
            ),
            Position(
                position_id="p2_aapl",
                snapshot_id="snap2",
                account_id="brk",
                symbol="AAPL",
                quantity=Decimal("5"),
                market_value=Decimal("500"),
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
        titles = {section.title for section in brief.sections}
        self.assertEqual(
            titles,
            {
                "Change since last",
                "Exposure & concentration",
                "Upcoming obligations",
                "Needs review",
            },
        )

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
