"""Tests for the Investment Policy Statement (L3) slice.

Covers the three things the slice claims: the IPS personalizes the L4 detector
thresholds, the compliance check reports pass/violation/blocked deterministically,
and writing an IPS is a receipt-backed round trip with a single active policy.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from finharness.allocation import record_allocation_candidates
from finharness.exposure import compute_exposure
from finharness.ips import (
    check_ips_compliance,
    current_ips,
    record_ips,
    thresholds_from_ips,
)
from finharness.statecore.models import (
    Account,
    CashflowEvent,
    Position,
    Snapshot,
)
from finharness.statecore.observations import ObservationThresholds
from finharness.statecore.store import init_state_core, write_records


class IpsSliceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _seed_portfolio(self, *, top_value: str, other_value: str, cash: str) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        positions = [
            Position(
                position_id="spy",
                snapshot_id="s",
                account_id="brk",
                symbol="SPY",
                quantity=Decimal("1"),
                market_value=Decimal(top_value),
                valuation_currency="USD",
                unit_price=Decimal(top_value),
                price_currency="USD",
                valued_at_utc="2026-06-19T00:00:00+00:00",
                price_source_ref="fixture:prices",
                valuation_status="valued",
            ),
            Position(
                position_id="aapl",
                snapshot_id="s",
                account_id="brk",
                symbol="AAPL",
                quantity=Decimal("1"),
                market_value=Decimal(other_value),
                valuation_currency="USD",
                unit_price=Decimal(other_value),
                price_currency="USD",
                valued_at_utc="2026-06-19T00:00:00+00:00",
                price_source_ref="fixture:prices",
                valuation_status="valued",
            ),
            Position(
                position_id="cash",
                snapshot_id="s",
                account_id="brk",
                symbol="USD",
                quantity=Decimal(cash),
                market_value=Decimal(cash),
                valuation_currency="USD",
                unit_price=Decimal("1"),
                price_currency="USD",
                valued_at_utc="2026-06-19T00:00:00+00:00",
                price_source_ref="fixture:prices",
                valuation_status="valued",
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

    # --- thresholds_from_ips ----------------------------------------------------------

    def test_thresholds_from_ips_overrides_defaults(self) -> None:
        ips = record_ips(
            liquidity_floor_months=9,
            max_single_holding_pct="0.30",
            cash_overweight_pct="0.55",
            high_interest_rate_pct="0.08",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        thresholds = thresholds_from_ips(ips)
        self.assertEqual(thresholds.cash_runway_target_months, 9.0)
        self.assertEqual(thresholds.concentration_pct, 0.30)
        self.assertEqual(thresholds.cash_overweight_pct, 0.55)
        self.assertEqual(thresholds.high_interest_rate_pct, 0.08)

    def test_thresholds_from_ips_keeps_defaults_when_optional_fields_absent(self) -> None:
        ips = record_ips(
            liquidity_floor_months=6,
            max_single_holding_pct="0.40",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        thresholds = thresholds_from_ips(ips)
        defaults = ObservationThresholds()
        self.assertEqual(thresholds.cash_overweight_pct, defaults.cash_overweight_pct)
        self.assertEqual(thresholds.high_interest_rate_pct, defaults.high_interest_rate_pct)

    # --- check_ips_compliance ---------------------------------------------------------

    def test_compliance_reports_pass_and_violation(self) -> None:
        # SPY 8000, AAPL 2000 -> SPY is 80% of the invested book; cash 5000 / 2000 = 2.5 mo.
        self._seed_portfolio(top_value="8000", other_value="2000", cash="5000")
        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        ips = record_ips(
            liquidity_floor_months=6,
            max_single_holding_pct="0.40",
            source_refs=["data/receipts/state-core/ips/receipt_seed.json"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        check = check_ips_compliance(report, ips)
        by_rule = {r.rule: r for r in check.results}
        self.assertEqual(by_rule["single_holding_cap"].status, "violation")
        self.assertEqual(by_rule["liquidity_floor"].status, "violation")
        self.assertIn("single_holding_cap", check.violations)
        self.assertIn("liquidity_floor", check.violations)
        self.assertFalse(check.execution_allowed)
        self.assertIn("data/receipts/state-core/ips/receipt_seed.json", check.source_refs)

    def test_compliance_passes_under_tolerant_policy(self) -> None:
        self._seed_portfolio(top_value="8000", other_value="2000", cash="5000")
        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        ips = record_ips(
            liquidity_floor_months=2,
            max_single_holding_pct="0.90",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        check = check_ips_compliance(report, ips)
        by_rule = {r.rule: r for r in check.results}
        self.assertEqual(by_rule["single_holding_cap"].status, "pass")
        self.assertEqual(by_rule["liquidity_floor"].status, "pass")
        self.assertEqual(check.violations, ())

    def test_compliance_blocks_when_data_unverifiable(self) -> None:
        # No portfolio snapshot or positions seeded: nothing to measure against.
        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        ips = record_ips(
            liquidity_floor_months=6,
            max_single_holding_pct="0.40",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        check = check_ips_compliance(report, ips)
        by_rule = {r.rule: r for r in check.results}
        self.assertEqual(by_rule["liquidity_floor"].status, "blocked")
        self.assertEqual(by_rule["single_holding_cap"].status, "blocked")
        self.assertIn("liquidity_floor", check.blocked)

    # --- record_ips / current_ips round trip ------------------------------------------

    def test_record_and_current_ips_round_trip(self) -> None:
        self.assertIsNone(current_ips(self.engine))
        ips = record_ips(
            liquidity_floor_months=6,
            max_single_holding_pct="0.40",
            source_refs=["data/receipts/state-core/imports/receipt_x.json"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        current = current_ips(self.engine)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.ips_id, ips.ips_id)
        self.assertFalse(current.execution_allowed)
        self.assertTrue(current.receipt_ref)
        self.assertTrue((self.receipt_root / "ips").exists())

    def test_recording_new_ips_supersedes_previous(self) -> None:
        first = record_ips(
            liquidity_floor_months=6,
            max_single_holding_pct="0.40",
            engine=self.engine,
            receipt_root=self.receipt_root,
            ips_id="ips_first",
        )
        second = record_ips(
            liquidity_floor_months=9,
            max_single_holding_pct="0.30",
            engine=self.engine,
            receipt_root=self.receipt_root,
            ips_id="ips_second",
        )
        current = current_ips(self.engine)
        assert current is not None
        self.assertEqual(current.ips_id, second.ips_id)
        self.assertNotEqual(current.ips_id, first.ips_id)

    # --- IPS personalizes the L4 detectors --------------------------------------------

    def test_allocation_uses_active_ips_thresholds(self) -> None:
        # AAPL 5500 of a 10000 invested book = 55% top weight; cash buffer healthy.
        self._seed_portfolio(top_value="4500", other_value="5500", cash="20000")

        # No IPS -> default 40% concentration flag fires.
        _, baseline = record_allocation_candidates(
            self.engine, receipt_root=self.receipt_root, as_of_date=date(2026, 6, 20)
        )
        self.assertIn("concentration_high", {w.proposal.kind for w in baseline})

        # A tolerant IPS (60% cap) makes the same book compliant -> detector goes quiet.
        record_ips(
            liquidity_floor_months=1,
            max_single_holding_pct="0.60",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        _, personalized = record_allocation_candidates(
            self.engine, receipt_root=self.receipt_root, as_of_date=date(2026, 6, 20)
        )
        self.assertNotIn("concentration_high", {w.proposal.kind for w in personalized})


if __name__ == "__main__":
    unittest.main()
