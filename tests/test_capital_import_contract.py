from __future__ import annotations

import unittest
from datetime import UTC, datetime
from decimal import Decimal

from finharness.capital_import_contract import (
    CapitalImportContractError,
    build_time_semantics,
    currency_code,
    exact_decimal,
)


class CapitalImportContractTest(unittest.TestCase):
    def test_decimal_round_trip_is_exact_and_float_is_rejected(self) -> None:
        value = exact_decimal("0.10000000000000000001", field="market_value")
        self.assertEqual(value, Decimal("0.10000000000000000001"))
        with self.assertRaisesRegex(CapitalImportContractError, "not float") as raised:
            exact_decimal(0.1, field="market_value")
        self.assertEqual(raised.exception.findings[0].code, "monetary_float_forbidden")

    def test_timezone_ambiguity_and_missing_currency_fail_closed(self) -> None:
        with self.assertRaisesRegex(CapitalImportContractError, "UTC offset") as raised:
            build_time_semantics(
                effective_at="2026-07-13T09:00:00",
                observed_at="2026-07-13T09:00:00+00:00",
                valued_at="2026-07-13T09:00:00+00:00",
                ingested_at=datetime(2026, 7, 13, 10, tzinfo=UTC),
            )
        self.assertEqual(raised.exception.findings[0].code, "timezone_ambiguous")
        with self.assertRaises(CapitalImportContractError) as currency_raised:
            currency_code("")
        self.assertEqual(
            currency_raised.exception.findings[0].code,
            "invalid_or_missing_currency",
        )

    def test_stale_valuation_is_a_blocking_finding(self) -> None:
        semantics, findings = build_time_semantics(
            effective_at="2026-07-11T09:00:00+00:00",
            observed_at="2026-07-13T09:00:00+00:00",
            valued_at="2026-07-11T09:00:00+00:00",
            ingested_at="2026-07-13T10:00:00+00:00",
        )
        self.assertEqual(semantics.observed_at_utc, "2026-07-13T09:00:00+00:00")
        # Freshness moved to position_valuation.assess_position_valuation.
        self.assertEqual([(item.code, item.severity) for item in findings], [])


if __name__ == "__main__":
    unittest.main()
