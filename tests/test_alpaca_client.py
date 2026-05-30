from __future__ import annotations

import unittest

from finharness.alpaca_client import paper_experiment_config, query_path, summarize_account


class AlpacaClientTests(unittest.TestCase):
    def test_query_path_omits_none_and_encodes_params(self) -> None:
        path = query_path(
            "/v2/options/contracts",
            {
                "underlying_symbols": "SPY",
                "type": None,
                "limit": 20,
            },
        )

        self.assertEqual(path, "/v2/options/contracts?underlying_symbols=SPY&limit=20")

    def test_paper_experiment_config_is_broad_but_paper_scoped(self) -> None:
        config = paper_experiment_config()

        self.assertFalse(config["suspend_trade"])
        self.assertFalse(config["no_shorting"])
        self.assertTrue(config["fractional_trading"])
        self.assertEqual(config["max_margin_multiplier"], "4")
        self.assertEqual(config["max_options_trading_level"], 3)

    def test_summarize_account_exposes_relevant_capability_fields(self) -> None:
        summary = summarize_account(
            {
                "id": "paper-id",
                "status": "ACTIVE",
                "options_approved_level": 3,
                "options_trading_level": 2,
                "trading_blocked": False,
            }
        )

        self.assertEqual(summary["account_id"], "paper-id")
        self.assertEqual(summary["options_approved_level"], 3)
        self.assertEqual(summary["options_trading_level"], 2)
        self.assertFalse(summary["trading_blocked"])


if __name__ == "__main__":
    unittest.main()
