from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from finharness.position_valuation import (
    reconcile_position_totals,
    valuation_blockers,
)
from finharness.statecore.models import Position

NOW = datetime(2026, 7, 13, 12, tzinfo=UTC)


def position(position_id: str, **overrides: object) -> Position:
    values: dict[str, object] = {
        "position_id": position_id,
        "snapshot_id": "snap",
        "account_id": "acct",
        "instrument_id": f"instr_{position_id}",
        "symbol": position_id.upper(),
        "quantity": Decimal("2"),
        "market_value": Decimal("100"),
        "valuation_currency": "USD",
        "unit_price": Decimal("50"),
        "price_currency": "USD",
        "valued_at_utc": "2026-07-13T11:00:00+00:00",
        "price_source_ref": "receipt:prices",
        "valuation_status": "valued",
    }
    values.update(overrides)
    return Position(**values)  # type: ignore[arg-type]


class PositionValuationTest(unittest.TestCase):
    def test_usd_components_reconcile_to_one_declared_base_currency(self) -> None:
        totals = reconcile_position_totals([position("spy"), position("qqq")])

        self.assertTrue(totals.admitted)
        self.assertEqual(totals.base_currency, "USD")
        self.assertEqual(totals.unified_total, Decimal("200"))
        self.assertEqual(totals.per_currency_totals, {"USD": Decimal("200")})

    def test_mixed_unconverted_state_has_no_unified_total(self) -> None:
        eur = position(
            "eur",
            market_value=None,
            valuation_currency="USD",
            unit_price=Decimal("40"),
            price_currency="EUR",
            valuation_status="fx_missing",
        )

        totals = reconcile_position_totals([position("spy"), eur])

        self.assertIsNone(totals.unified_total)
        self.assertIn("eur:valuation_fx_missing", totals.blockers)
        self.assertIn("eur:market_value_missing", totals.blockers)

    def test_converted_fx_requires_evidence_and_reconciles(self) -> None:
        converted = position(
            "eur",
            market_value=Decimal("110"),
            price_currency="EUR",
            fx_rate=Decimal("1.1"),
            fx_as_of_utc="2026-07-13T11:00:00+00:00",
            fx_source_ref="receipt:fx",
            valuation_status="valued_converted",
        )

        totals = reconcile_position_totals([converted])

        self.assertTrue(totals.admitted)
        self.assertEqual(totals.unified_total, Decimal("110"))

    def test_unpriced_and_legacy_unknown_positions_block(self) -> None:
        unpriced = position(
            "unpriced",
            market_value=None,
            unit_price=None,
            price_source_ref=None,
            valuation_status="unpriced",
        )
        legacy = Position(
            position_id="legacy",
            snapshot_id="snap",
            account_id="acct",
            symbol="OLD",
            quantity=Decimal("1"),
            market_value=Decimal("25"),
        )

        self.assertIn("valuation_unpriced", valuation_blockers(unpriced))
        self.assertIn("valuation_unknown_legacy", valuation_blockers(legacy))
        self.assertIsNone(reconcile_position_totals([unpriced, legacy]).unified_total)

    def test_stale_price_and_fx_block_time_sensitive_use(self) -> None:
        stale = position(
            "stale",
            market_value=Decimal("110"),
            price_currency="EUR",
            fx_rate=Decimal("1.1"),
            fx_as_of_utc="2026-07-10T11:00:00+00:00",
            fx_source_ref="receipt:fx",
            valued_at_utc="2026-07-10T11:00:00+00:00",
            valuation_status="valued_converted",
        )

        blockers = valuation_blockers(stale, evaluated_at=NOW, max_age=timedelta(hours=24))

        self.assertIn("market_price_stale", blockers)
        self.assertIn("fx_stale", blockers)

    def test_non_reconciling_components_block(self) -> None:
        bad = position("bad", market_value=Decimal("99"))

        self.assertIn("valuation_components_do_not_reconcile", valuation_blockers(bad))


if __name__ == "__main__":
    unittest.main()
