from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.restricted_symbols import (
    is_restricted,
    load_restricted_symbol_list,
    tradability_for_symbol,
)


class RestrictedSymbolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.restricted_path = self.root / "restricted-symbols.json"
        self.restricted_path.write_text(
            json.dumps(
                {
                    "schema_version": "finharness.restricted_symbols.v1",
                    "restricted_list_version": "test-deny-v1",
                    "updated_at_utc": "2026-06-18T00:00:00+00:00",
                    "entries": [
                        {
                            "symbol": "SPY",
                            "reason": "manual local deny-list test",
                            "added_utc": "2026-06-18T00:00:00+00:00",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        self.addCleanup(self.tmp.cleanup)

    def test_restricted_symbol_matches_normalized_symbol_and_version(self) -> None:
        restricted = is_restricted("spy", restricted_list_path=self.restricted_path)
        clean = is_restricted("QQQ", restricted_list_path=self.restricted_path)

        self.assertTrue(restricted.restricted)
        self.assertEqual(restricted.normalized_symbol, "SPY")
        self.assertEqual(restricted.restricted_list_version, "test-deny-v1")
        self.assertFalse(clean.restricted)

    def test_unreadable_restricted_list_fails_closed(self) -> None:
        decision = is_restricted("SPY", restricted_list_path=self.root / "missing.json")

        self.assertTrue(decision.restricted)
        self.assertIn("refusing fail-closed", decision.reason)

    def test_alpaca_tradability_reads_asset_receipt(self) -> None:
        receipt = self.root / "alpaca-assets.json"
        receipt.write_text(
            json.dumps(
                {
                    "receipt_id": "receipt_assets",
                    "kind": "broker_read",
                    "assets": [
                        {"symbol": "SPY", "tradable": True},
                        {"symbol": "QQQ", "tradable": False},
                    ],
                }
            ),
            encoding="utf-8",
        )

        tradable = tradability_for_symbol("SPY", provider="alpaca", receipt_ref=receipt)
        not_tradable = tradability_for_symbol("QQQ", provider="alpaca", receipt_ref=receipt)
        unknown = tradability_for_symbol("AAPL", provider="alpaca", receipt_ref=receipt)

        self.assertTrue(tradable.allowed)
        self.assertEqual(tradable.status, "tradable")
        self.assertFalse(not_tradable.allowed)
        self.assertEqual(not_tradable.status, "not_tradable")
        self.assertFalse(unknown.allowed)
        self.assertEqual(unknown.status, "unknown")

    def test_okx_tradability_is_disclosed_as_not_applicable(self) -> None:
        decision = tradability_for_symbol("BTC-USDT", provider="okx")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.status, "not_applicable")

    def test_default_empty_list_loads(self) -> None:
        restricted_list = load_restricted_symbol_list()

        self.assertEqual(restricted_list.restricted_list_version, "local-empty-v1")


if __name__ == "__main__":
    unittest.main()
