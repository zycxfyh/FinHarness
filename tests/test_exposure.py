from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from finharness.exposure import compute_exposure
from finharness.statecore.models import (
    Account,
    CashflowEvent,
    InsurancePolicy,
    Liability,
    Position,
    Snapshot,
    TaxEvent,
)
from finharness.statecore.store import init_state_core, write_records


class ExposureTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = init_state_core(Path(self.tmp.name) / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def _valued_position(
        *,
        position_id: str,
        snapshot_id: str,
        account_id: str,
        symbol: str,
        quantity: str,
        market_value: str,
        currency: str = "USD",
        **overrides: object,
    ) -> Position:
        fields: dict[str, object] = {
            "position_id": position_id,
            "snapshot_id": snapshot_id,
            "account_id": account_id,
            "symbol": symbol,
            "quantity": Decimal(quantity),
            "market_value": Decimal(market_value),
            "valuation_currency": currency,
            "unit_price": Decimal(market_value) / Decimal(quantity),
            "price_currency": currency,
            "valued_at_utc": "2026-06-19T00:00:00+00:00",
            "price_source_ref": "fixture:prices",
            "valuation_status": "valued",
        }
        fields.update(overrides)
        return Position(**fields)

    def _seed(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brokerage")
        snapshot = Snapshot(
            snapshot_id="snap1", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        positions = [
            self._valued_position(
                position_id="p_spy",
                snapshot_id="snap1",
                account_id="brk",
                symbol="SPY",
                quantity="10",
                market_value="8000",
            ),
            self._valued_position(
                position_id="p_aapl",
                snapshot_id="snap1",
                account_id="brk",
                symbol="AAPL",
                quantity="5",
                market_value="2000",
            ),
            self._valued_position(
                position_id="p_cash",
                snapshot_id="snap1",
                account_id="brk",
                symbol="USD",
                quantity="5000",
                market_value="5000",
            ),
        ]
        liabilities = [
            Liability(
                liability_id="mortgage",
                name="Mortgage",
                liability_type="mortgage",
                balance=Decimal("100000"),
                currency="USD",
                interest_rate=Decimal("0.04"),
            ),
            Liability(
                liability_id="card",
                name="Card",
                liability_type="card",
                balance=Decimal("5000"),
                currency="USD",
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
                amount=Decimal("-7000"),
                currency="USD",
                event_date="2026-07-01",
                category="expense",
                frequency="monthly",
            ),
        ]
        tax = TaxEvent(
            tax_event_id="q3",
            event_type="estimated_payment",
            jurisdiction="US",
            due_date="2026-07-15",
            estimated_amount=Decimal("1200"),
            currency="USD",
        )
        insurance = InsurancePolicy(
            policy_id="home",
            policy_type="home",
            provider="Example Mutual",
            coverage_amount=Decimal("500000"),
            premium_amount=Decimal("300"),
            currency="USD",
            renewal_date="2026-08-01",
        )
        write_records(
            [account, snapshot, *positions, *liabilities, *cashflows, tax, insurance],
            engine=self.engine,
        )

    def test_exposure_map_aggregates_net_worth_concentration_runway_and_obligations(self) -> None:
        self._seed()

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))

        self.assertFalse(report.execution_allowed)
        self.assertEqual(report.base_currency, "USD")
        self.assertEqual(report.total_assets, 15000.0)
        self.assertEqual(report.total_liabilities, 105000.0)
        self.assertEqual(report.net_worth, -90000.0)
        self.assertEqual(report.cash_total, 5000.0)

        # Concentration is over the securities book (cash excluded): SPY and AAPL
        # only. SPY 8000 / (8000+2000) = 80%, crossing the 40% flag.
        self.assertEqual(report.holding_count, 2)
        self.assertEqual(report.holdings[0].symbol, "SPY")
        self.assertAlmostEqual(report.top_holding_weight, 8000 / 10000, places=6)
        self.assertTrue(report.concentration_flagged)
        self.assertAlmostEqual(report.concentration_hhi, 0.8**2 + 0.2**2, places=4)

        # Rate exposure: only the mortgage carries a rate.
        self.assertEqual(report.interest_bearing_debt_total, 100000.0)
        self.assertAlmostEqual(report.weighted_avg_interest_rate or 0.0, 0.04, places=6)
        self.assertEqual(report.annual_interest_estimate, 4000.0)

        # Cash runway (emergency-fund standard): monthly expenses 7000, cash 5000
        # -> 5000/7000 months of expenses covered; net is income 5000 - expenses 7000.
        self.assertEqual(report.monthly_net_cashflow, -2000.0)
        self.assertAlmostEqual(report.cash_runway_months or 0.0, 5000 / 7000, places=6)

        # Upcoming obligations within 90 days, sorted by date.
        kinds = {item.kind for item in report.upcoming_obligations}
        self.assertEqual(kinds, {"cashflow", "tax_event", "insurance_renewal"})
        self.assertEqual(report.upcoming_obligations[0].due_date, "2026-07-01")
        self.assertEqual(report.data_gaps, ())

    def test_negative_cash_does_not_break_concentration_weights(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        positions = [
            self._valued_position(
                position_id="spy",
                snapshot_id="s",
                account_id="brk",
                symbol="SPY",
                quantity="10",
                market_value="6000",
            ),
            self._valued_position(
                position_id="cash",
                snapshot_id="s",
                account_id="brk",
                symbol="USD",
                quantity="-5000",
                market_value="-5000",
            ),
        ]
        write_records([account, snapshot, *positions], engine=self.engine)

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))

        self.assertEqual(report.total_assets, 1000.0)
        # Long book is 100% SPY; concentration must stay in [0, 1] despite the
        # negative cash position (which previously made the weight 600%).
        self.assertEqual(report.top_holding_weight, 1.0)
        self.assertEqual(report.concentration_hhi, 1.0)

    def test_empty_state_does_not_invent_zero_net_worth(self) -> None:
        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))

        self.assertFalse(report.asset_valuation_admitted)
        self.assertFalse(report.net_worth_admitted)
        self.assertIsNone(report.total_assets)
        self.assertIsNone(report.total_liabilities)
        self.assertIsNone(report.net_worth)
        self.assertEqual(report.holding_count, 0)
        self.assertIsNone(report.cash_runway_months)
        self.assertIn(
            "portfolio_snapshot_missing",
            report.asset_valuation_blockers,
        )

    def test_mixed_currencies_preserve_components_but_block_unified_claims(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        positions = [
            self._valued_position(
                position_id="usd",
                snapshot_id="s",
                account_id="brk",
                symbol="SPY",
                quantity="1",
                market_value="100",
            ),
            self._valued_position(
                position_id="jpy",
                snapshot_id="s",
                account_id="brk",
                symbol="7203",
                quantity="1",
                market_value="20000",
                currency="JPY",
            ),
        ]
        write_records([account, snapshot, *positions], engine=self.engine)

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))

        self.assertFalse(report.asset_valuation_admitted)
        self.assertFalse(report.net_worth_admitted)
        self.assertIsNone(report.total_assets)
        self.assertIsNone(report.net_worth)
        self.assertEqual(report.per_currency_totals, {"JPY": 20000.0, "USD": 100.0})
        self.assertIn("mixed_valuation_currencies", report.asset_valuation_blockers)
        self.assertIsNone(report.concentration_hhi)
        self.assertIsNone(report.top_holding_weight)
        self.assertFalse(report.concentration_flagged)

    def test_nonconforming_position_blocks_all_unified_outputs(self) -> None:
        cases = {
            "unknown_legacy": {
                "valuation_status": "unknown_legacy",
                "valuation_currency": None,
                "unit_price": None,
                "price_currency": None,
                "valued_at_utc": None,
                "price_source_ref": None,
            },
            "unpriced": {
                "valuation_status": "unpriced",
                "unit_price": None,
            },
            "fx_missing": {
                "valuation_status": "fx_missing",
                "price_currency": "EUR",
            },
            "stale": {"valuation_status": "stale"},
            "arithmetic_mismatch": {"unit_price": Decimal("99")},
        }
        for index, (name, overrides) in enumerate(cases.items()):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                engine = init_state_core(Path(tmp) / "state-core.sqlite")
                self.addCleanup(engine.dispose)
                account = Account(
                    account_id="brk", kind="broker", venue="m", display_name="Brk"
                )
                snapshot = Snapshot(
                    snapshot_id=f"s{index}",
                    kind="portfolio",
                    as_of_utc="2026-06-19T00:00:00+00:00",
                )
                position = self._valued_position(
                    position_id=f"p{index}",
                    snapshot_id=snapshot.snapshot_id,
                    account_id="brk",
                    symbol="SPY",
                    quantity="1",
                    market_value="100",
                    **overrides,
                )
                write_records([account, snapshot, position], engine=engine)

                report = compute_exposure(engine, as_of_date=date(2026, 6, 20))

                self.assertFalse(report.asset_valuation_admitted)
                self.assertIsNone(report.total_assets)
                self.assertIsNone(report.net_worth)
                self.assertIsNone(report.concentration_hhi)

    def test_liability_currency_mismatch_blocks_net_worth_only(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        position = self._valued_position(
            position_id="usd",
            snapshot_id="s",
            account_id="brk",
            symbol="SPY",
            quantity="1",
            market_value="100",
        )
        liability = Liability(
            liability_id="jpy-debt",
            name="JPY debt",
            liability_type="loan",
            balance=Decimal("10000"),
            currency="JPY",
        )
        write_records([account, snapshot, position, liability], engine=self.engine)

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))

        self.assertTrue(report.asset_valuation_admitted)
        self.assertEqual(report.total_assets, 100.0)
        self.assertFalse(report.net_worth_admitted)
        self.assertIsNone(report.total_liabilities)
        self.assertIsNone(report.net_worth)
        self.assertEqual(report.liability_per_currency_totals, {"JPY": 10000.0})
        self.assertIn(
            "liability_currency_mismatch:JPY:USD",
            report.net_worth_blockers,
        )


if __name__ == "__main__":
    unittest.main()
