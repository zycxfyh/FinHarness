from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from finharness.market_data_graph import market_data_graph, run_market_data_graph


def sample_history() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-03"]),
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.5],
            "close": [101.0, 102.5],
            "volume": [1000, 1200],
        }
    )


class MarketDataGraphTest(unittest.TestCase):
    def test_graph_compiles(self) -> None:
        self.assertIsNotNone(market_data_graph)

    def test_graph_runs_strict_layer_flow(self) -> None:
        with patch(
            "finharness.market_data_graph.fetch_yfinance_history",
            return_value=sample_history(),
        ):
            result = run_market_data_graph(
                symbol="SPY",
                start="2026-01-01",
                end="2026-01-05",
                write_catalog=False,
            )

        final = result["final"]
        self.assertEqual(final["workflow"], "langgraph_market_data_v1")
        self.assertEqual(final["symbol"], "SPY")
        self.assertEqual(final["row_count"], 2)
        self.assertTrue(final["quality_ok"])
        self.assertFalse(final["execution_allowed"])
        self.assertEqual(final["consumer_handoff"]["consumer"], "indicator_layer_research_review")
        self.assertEqual(final["review_hook"]["status"], "open")
        self.assertTrue(result["snapshot"]["receipt_ref"])


if __name__ == "__main__":
    unittest.main()
