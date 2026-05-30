from __future__ import annotations

import unittest

from finharness.finance_graph import finance_graph, run_finance_graph


class FinanceGraphTest(unittest.TestCase):
    def test_graph_compiles(self) -> None:
        self.assertIsNotNone(finance_graph)

    def test_graph_runs_data_entry_and_eval(self) -> None:
        result = run_finance_graph("SPY", "2025-01-01", "2025-06-30")
        self.assertEqual(result["workflow"]["symbol"], "SPY")
        self.assertEqual(result["workflow"]["not_data_source"], "TradingView/TV")
        self.assertTrue(result["eval"]["ok"], result["eval"])
        self.assertTrue(result["final"]["eval_ok"])


if __name__ == "__main__":
    unittest.main()

