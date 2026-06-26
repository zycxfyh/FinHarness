from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from finharness.market_access_ledger import (
    LedgerEntry,
    MarketAccessDecision,
    MarketAccessKey,
    MarketAccessLimit,
    evaluate_market_access,
    load_market_access_ledger,
    record_consumption,
    usage_in_window,
    window_id,
)


class MarketAccessLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger_path = self.root / "state" / "ledger.json"
        self.receipts = self.root / "receipts"
        self.key = MarketAccessKey(
            environment="paper",
            venue="paper_review",
            operator="operator",
            account="paper_account",
            symbol="SPY",
        )
        self.limit = MarketAccessLimit(max_window_notional=100.0, max_window_order_count=2)
        self.now = datetime(2026, 6, 16, 12, 0, tzinfo=UTC)
        self.addCleanup(self.tmp.cleanup)

    def entry(self, notional: float, *, days_ago: int = 0) -> LedgerEntry:
        created_at = self.now - timedelta(days=days_ago)
        return LedgerEntry(
            entry_id=f"entry_{notional}_{days_ago}",
            window_id=window_id(created_at),
            key=self.key,
            notional=notional,
            created_at_utc=created_at.isoformat(),
        )

    def test_aggregate_notional_blocks_second_under_cap_order(self) -> None:
        decision = evaluate_market_access(
            key=self.key,
            notional=50.0,
            limit=self.limit,
            ledger=[self.entry(60.0)],
            now=self.now,
        )

        self.assertFalse(decision.allowed_within_limit)
        self.assertTrue(
            any("aggregate window notional" in reason for reason in decision.blocking_reasons)
        )

    def test_order_count_ceiling_blocks_next_order(self) -> None:
        decision = evaluate_market_access(
            key=self.key,
            notional=1.0,
            limit=self.limit,
            ledger=[self.entry(10.0), self.entry(20.0)],
            now=self.now,
        )

        self.assertFalse(decision.allowed_within_limit)
        self.assertIn("aggregate window order count exceeded", decision.blocking_reasons)

    def test_fail_closed_on_unbounded_notional_and_missing_limit(self) -> None:
        none_notional = evaluate_market_access(
            key=self.key,
            notional=None,
            limit=self.limit,
            ledger=[],
            now=self.now,
        )
        zero_notional = evaluate_market_access(
            key=self.key,
            notional=0,
            limit=self.limit,
            ledger=[],
            now=self.now,
        )
        missing_limit = evaluate_market_access(
            key=self.key,
            notional=1.0,
            limit=None,
            ledger=[],
            now=self.now,
        )

        self.assertFalse(none_notional.allowed_within_limit)
        self.assertFalse(zero_notional.allowed_within_limit)
        self.assertFalse(missing_limit.allowed_within_limit)
        self.assertIn(
            "no pre-set aggregate limit configured; refusing fail-closed",
            missing_limit.blocking_reasons,
        )

    def test_within_limit_reports_remaining(self) -> None:
        decision = evaluate_market_access(
            key=self.key,
            notional=25.0,
            limit=self.limit,
            ledger=[self.entry(40.0)],
            now=self.now,
        )

        self.assertTrue(decision.allowed_within_limit)
        self.assertEqual(decision.used_notional, 40.0)
        self.assertEqual(decision.remaining_notional_after, 35.0)
        self.assertEqual(decision.remaining_orders_after, 0)
        self.assertFalse(decision.execution_allowed)

    def test_window_rollover_ignores_prior_day(self) -> None:
        ledger = [self.entry(90.0, days_ago=1)]
        used, count = usage_in_window(ledger, self.key, window_id(self.now))
        decision = evaluate_market_access(
            key=self.key,
            notional=90.0,
            limit=self.limit,
            ledger=ledger,
            now=self.now,
        )

        self.assertEqual((used, count), (0, 0))
        self.assertTrue(decision.allowed_within_limit)

    def test_evaluate_is_read_only_and_record_writes_receipt(self) -> None:
        evaluate_market_access(
            key=self.key,
            notional=25.0,
            limit=self.limit,
            ledger=[],
            now=self.now,
        )
        self.assertFalse(self.ledger_path.exists())

        entry = record_consumption(
            key=self.key,
            notional=25.0,
            limit=self.limit,
            now=self.now,
            state_root=self.ledger_path,
            receipt_root=self.receipts,
        )

        loaded = load_market_access_ledger(self.ledger_path)
        self.assertEqual([item.entry_id for item in loaded], [entry.entry_id])
        receipt_payload = json.loads(
            (self.receipts / f"receipt_{entry.entry_id}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt_payload["kind"], "market_access_consumption")
        self.assertEqual(receipt_payload["window_usage_after"]["remaining_notional"], 75.0)
        self.assertFalse(receipt_payload["execution_allowed"])

    def test_decision_cannot_be_validated_with_execution_authority(self) -> None:
        with self.assertRaises(ValidationError):
            MarketAccessDecision.model_validate(
                {
                    "allowed_within_limit": True,
                    "window_id": "2026-06-16",
                    "used_notional": 0.0,
                    "remaining_notional_after": 1.0,
                    "used_order_count": 0,
                    "remaining_orders_after": 1,
                    "execution_allowed": True,
                }
            )


if __name__ == "__main__":
    unittest.main()
