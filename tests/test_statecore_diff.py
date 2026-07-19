from __future__ import annotations

import unittest
from decimal import Decimal

from finharness.statecore.diff import diff_snapshots
from finharness.statecore.models import Account, Position, Proposal, ReceiptIndex, Snapshot
from finharness.statecore.store import (
    StateCoreStoreError,
    read_all,
    write_records,
)
from tests._statecore_fixtures import StateCoreFixture


class StateCoreDiffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = StateCoreFixture()
        self.engine = self.fx.engine
        self.addCleanup(self.fx.cleanup)

    def _seed_portfolio_snapshots(self) -> None:
        account = Account(
            account_id="acct_diff",
            kind="broker",
            venue="alpaca-paper",
            display_name="Diff Account",
            source_refs=["data/receipts/before.json"],
        )
        before = Snapshot(
            snapshot_id="snap_before",
            kind="portfolio",
            as_of_utc="2026-06-17T09:00:00+00:00",
            payload={"source": "test_fixture"},
            source_refs=["data/receipts/before.json"],
        )
        after = Snapshot(
            snapshot_id="snap_after",
            kind="portfolio",
            as_of_utc="2026-06-17T10:00:00+00:00",
            payload={"source": "test_fixture"},
            source_refs=["data/receipts/after.json"],
        )
        positions = [
            Position(
                position_id="pos_before_spy",
                snapshot_id=before.snapshot_id,
                account_id=account.account_id,
                symbol="SPY",
                quantity=1.0,
                market_value=100.0,
                valuation_currency="USD",
                unit_price=100.0,
                price_currency="USD",
                valued_at_utc="2026-06-17T09:00:00+00:00",
                price_source_ref="data/receipts/before.json",
                valuation_status="valued",
                source_refs=["data/receipts/before.json"],
            ),
            Position(
                position_id="pos_before_qqq",
                snapshot_id=before.snapshot_id,
                account_id=account.account_id,
                symbol="QQQ",
                quantity=2.0,
                market_value=200.0,
                valuation_currency="USD",
                unit_price=100.0,
                price_currency="USD",
                valued_at_utc="2026-06-17T09:00:00+00:00",
                price_source_ref="data/receipts/before.json",
                valuation_status="valued",
                source_refs=["data/receipts/before.json"],
            ),
            Position(
                position_id="pos_before_msft",
                snapshot_id=before.snapshot_id,
                account_id=account.account_id,
                symbol="MSFT",
                quantity=3.0,
                market_value=300.0,
                valuation_currency="USD",
                unit_price=100.0,
                price_currency="USD",
                valued_at_utc="2026-06-17T09:00:00+00:00",
                price_source_ref="data/receipts/before.json",
                valuation_status="valued",
                source_refs=["data/receipts/before.json"],
            ),
            Position(
                position_id="pos_after_spy",
                snapshot_id=after.snapshot_id,
                account_id=account.account_id,
                symbol="SPY",
                quantity=1.5,
                market_value=155.0,
                valuation_currency="USD",
                unit_price=Decimal("103.3333333333333333333333333"),
                price_currency="USD",
                valued_at_utc="2026-06-17T10:00:00+00:00",
                price_source_ref="data/receipts/after.json",
                valuation_status="valued",
                source_refs=["data/receipts/after.json"],
            ),
            Position(
                position_id="pos_after_msft",
                snapshot_id=after.snapshot_id,
                account_id=account.account_id,
                symbol="MSFT",
                quantity=3.0,
                market_value=300.0,
                valuation_currency="USD",
                unit_price=100.0,
                price_currency="USD",
                valued_at_utc="2026-06-17T10:00:00+00:00",
                price_source_ref="data/receipts/after.json",
                valuation_status="valued",
                source_refs=["data/receipts/after.json"],
            ),
            Position(
                position_id="pos_after_aapl",
                snapshot_id=after.snapshot_id,
                account_id=account.account_id,
                symbol="AAPL",
                quantity=4.0,
                market_value=80.0,
                valuation_currency="USD",
                unit_price=20.0,
                price_currency="USD",
                valued_at_utc="2026-06-17T10:00:00+00:00",
                price_source_ref="data/receipts/after.json",
                valuation_status="valued",
                source_refs=["data/receipts/after.json"],
            ),
        ]
        write_records([account, before, after, *positions], engine=self.engine)

    def test_diff_reports_added_removed_changed_and_exposure_delta(self) -> None:
        self._seed_portfolio_snapshots()

        diff = diff_snapshots("snap_before", "snap_after", engine=self.engine)

        self.assertEqual(diff.before_snapshot_id, "snap_before")
        self.assertEqual(diff.after_snapshot_id, "snap_after")
        self.assertEqual(diff.total_market_value_before, 600.0)
        self.assertEqual(diff.total_market_value_after, 535.0)
        self.assertEqual(diff.total_market_value_delta, -65.0)
        self.assertFalse(diff.execution_allowed)
        self.assertEqual(
            diff.source_refs,
            ("data/receipts/after.json", "data/receipts/before.json"),
        )

        self.assertEqual([change.symbol for change in diff.added], ["AAPL"])
        self.assertEqual(diff.added[0].before_quantity, 0.0)
        self.assertEqual(diff.added[0].after_quantity, 4.0)
        self.assertEqual(diff.added[0].market_value_delta, 80.0)
        self.assertEqual(diff.added[0].change_reason, "transaction_like")

        self.assertEqual([change.symbol for change in diff.removed], ["QQQ"])
        self.assertEqual(diff.removed[0].before_quantity, 2.0)
        self.assertEqual(diff.removed[0].after_quantity, 0.0)
        self.assertEqual(diff.removed[0].market_value_delta, -200.0)
        self.assertEqual(diff.removed[0].change_reason, "deletion")

        self.assertEqual([change.symbol for change in diff.changed], ["SPY"])
        self.assertEqual(diff.changed[0].quantity_delta, 0.5)
        self.assertEqual(diff.changed[0].market_value_delta, 55.0)
        self.assertEqual(diff.changed[0].change_reason, "transaction_like")
        self.assertEqual(diff.as_dict()["changed"][0]["change_type"], "changed")

    def test_diff_is_read_only_and_does_not_create_decision_artifacts(self) -> None:
        self._seed_portfolio_snapshots()

        diff = diff_snapshots("snap_before", "snap_after", engine=self.engine)

        self.assertEqual(read_all(Proposal, engine=self.engine), [])
        self.assertEqual(read_all(ReceiptIndex, engine=self.engine), [])
        self.assertIn("Descriptive state diff only.", diff.non_claims)
        self.assertIn("Not investment advice.", diff.non_claims)
        self.assertIn("Not trading authorization.", diff.non_claims)

    def test_market_value_only_change_is_classified_as_price_fx(self) -> None:
        account = Account(
            account_id="acct_price",
            kind="broker",
            venue="manual",
            display_name="Price Account",
        )
        before = Snapshot(snapshot_id="snap_price_before", kind="portfolio")
        after = Snapshot(snapshot_id="snap_price_after", kind="portfolio")
        positions = [
            Position(
                position_id="pos_price_before",
                snapshot_id=before.snapshot_id,
                account_id=account.account_id,
                symbol="SPY",
                quantity=Decimal("2"),
                market_value=Decimal("200"),
                valuation_currency="USD",
                unit_price=Decimal("100"),
                price_currency="USD",
                valued_at_utc="2026-06-17T09:00:00+00:00",
                price_source_ref="before",
                valuation_status="valued",
            ),
            Position(
                position_id="pos_price_after",
                snapshot_id=after.snapshot_id,
                account_id=account.account_id,
                symbol="SPY",
                quantity=Decimal("2"),
                market_value=Decimal("210"),
                valuation_currency="USD",
                unit_price=Decimal("105"),
                price_currency="USD",
                valued_at_utc="2026-06-17T10:00:00+00:00",
                price_source_ref="after",
                valuation_status="valued",
            ),
        ]
        write_records([account, before, after, *positions], engine=self.engine)

        diff = diff_snapshots(before.snapshot_id, after.snapshot_id, engine=self.engine)

        self.assertEqual(diff.changed[0].change_reason, "price_fx")

    def test_missing_snapshot_fails_closed(self) -> None:
        self._seed_portfolio_snapshots()

        with self.assertRaises(StateCoreStoreError):
            diff_snapshots("snap_before", "snap_missing", engine=self.engine)

    def test_non_portfolio_snapshot_fails_closed(self) -> None:
        account = Account(
            account_id="acct_diff",
            kind="broker",
            venue="manual",
            display_name="Diff Account",
        )
        before = Snapshot(snapshot_id="snap_before", kind="portfolio")
        after = Snapshot(snapshot_id="snap_after", kind="research")
        write_records([account, before, after], engine=self.engine)

        with self.assertRaises(StateCoreStoreError):
            diff_snapshots("snap_before", "snap_after", engine=self.engine)


if __name__ == "__main__":
    unittest.main()
