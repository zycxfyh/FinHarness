from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import finharness.portfolio_risk as portfolio_risk
from finharness.portfolio_risk import (
    RiskfolioAllocationSummary,
    concentration_request_from_allocation,
    optimize_riskfolio_allocation,
    returns_from_close_prices,
)


def sample_returns() -> pd.DataFrame:
    rng = np.random.default_rng(20260614)
    return pd.DataFrame(
        {
            "SPY": rng.normal(0.0005, 0.010, size=120),
            "QQQ": rng.normal(0.0007, 0.014, size=120),
            "TLT": rng.normal(0.0002, 0.006, size=120),
        }
    )


class PortfolioRiskTest(unittest.TestCase):
    def test_riskfolio_allocation_uses_riskfolio_and_never_authorizes_execution(
        self,
    ) -> None:
        with patch(
            "finharness.portfolio_risk.rp.Portfolio",
            wraps=portfolio_risk.rp.Portfolio,
        ) as portfolio:
            summary = optimize_riskfolio_allocation(sample_returns(), concentration_cap=0.7)

        self.assertTrue(portfolio.called)
        self.assertEqual(summary.backend, "Riskfolio-Lib.Portfolio.optimization")
        self.assertAlmostEqual(summary.weight_sum, 1.0, places=6)
        self.assertLessEqual(summary.max_weight, 0.70000001)
        self.assertTrue(summary.concentration_ok)
        self.assertFalse(summary.execution_allowed)

    def test_infeasible_concentration_cap_is_rejected_before_optimization(self) -> None:
        with self.assertRaises(ValueError):
            optimize_riskfolio_allocation(sample_returns(), concentration_cap=0.2)

    def test_returns_from_close_prices_requires_positive_numeric_prices(self) -> None:
        with self.assertRaises(ValueError):
            returns_from_close_prices(pd.DataFrame({"SPY": [100, 0], "QQQ": [100, 101]}))

    def test_concentration_request_uses_symbol_weight_only(self) -> None:
        summary = RiskfolioAllocationSummary(
            backend="Riskfolio-Lib.Portfolio.optimization",
            model="Classic",
            risk_measure="MV",
            objective="Sharpe",
            weights={"NVDA": 0.18, "SPY": 0.82},
            weight_sum=1.0,
            max_weight=0.82,
            concentration_cap=0.90,
            concentration_ok=True,
            execution_allowed=False,
        )

        self.assertEqual(concentration_request_from_allocation(summary, "nvda"), 0.18)
        self.assertEqual(concentration_request_from_allocation(summary, "MSFT"), 0.0)


if __name__ == "__main__":
    unittest.main()
