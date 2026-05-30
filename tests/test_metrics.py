from __future__ import annotations

import unittest

from finharness.metrics import max_drawdown, pct_returns, summarize


class MetricsTest(unittest.TestCase):
    def test_pct_returns(self) -> None:
        returns = pct_returns([100.0, 110.0, 99.0])
        self.assertAlmostEqual(returns[0], 0.1)
        self.assertAlmostEqual(returns[1], -0.1)

    def test_max_drawdown(self) -> None:
        self.assertAlmostEqual(max_drawdown([100.0, 120.0, 90.0, 130.0]), -0.25)

    def test_summarize_requires_prices(self) -> None:
        with self.assertRaises(ValueError):
            summarize([100.0])


if __name__ == "__main__":
    unittest.main()
