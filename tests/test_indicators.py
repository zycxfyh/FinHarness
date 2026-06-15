from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

import finharness.indicators.macd as macd_module
import finharness.indicators.squeeze as squeeze_module
from finharness.indicators.macd import compute_macd
from finharness.indicators.shared import latest_snapshot
from finharness.indicators.smc import compute_smc
from finharness.indicators.squeeze import compute_squeeze_momentum


def sample_history() -> pd.DataFrame:
    rows = []
    for index in range(80):
        close = 100.0 + index * 0.5
        rows.append(
            {
                "date": f"2025-01-{index % 28 + 1:02d}",
                "open": close - 0.2,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000 + index,
            }
        )
    return pd.DataFrame(rows)


class IndicatorTests(unittest.TestCase):
    def test_macd_outputs_expected_columns(self) -> None:
        with patch(
            "finharness.indicators.macd.talib.MACD",
            wraps=macd_module.talib.MACD,
        ) as macd:
            result = compute_macd(sample_history())

        self.assertEqual(macd_module.MACD_BACKEND, "TA-Lib.MACD")
        self.assertTrue(macd.called)
        self.assertIn("macd", result.columns)
        self.assertIn("macd_signal", result.columns)
        self.assertIn("macd_hist", result.columns)
        self.assertIn(result.iloc[-1]["macd_bias"], {"bullish", "bearish"})

    def test_squeeze_outputs_expected_state(self) -> None:
        with patch(
            "finharness.indicators.squeeze.talib.BBANDS",
            wraps=squeeze_module.talib.BBANDS,
        ) as bbands, patch(
            "finharness.indicators.squeeze.talib.LINEARREG",
            wraps=squeeze_module.talib.LINEARREG,
        ) as linearreg:
            result = compute_squeeze_momentum(sample_history())

        self.assertEqual(
            squeeze_module.SQUEEZE_BACKEND,
            "TA-Lib.BBANDS/TRANGE/SMA/LINEARREG",
        )
        self.assertTrue(bbands.called)
        self.assertTrue(linearreg.called)
        self.assertIn("squeeze_state", result.columns)
        self.assertIn(
            result.iloc[-1]["squeeze_momentum_state"],
            {
                "positive_rising",
                "positive_falling",
                "negative_falling",
                "negative_rising",
                "unknown",
            },
        )

    def test_smc_detects_bias(self) -> None:
        result = compute_smc(sample_history(), zigzag_len=9)
        self.assertIn(result.iloc[-1]["smc_market_bias"], {"bullish", "bearish", "neutral"})
        self.assertIn("smc_swing_high", result.columns)

    def test_single_indicator_snapshot_never_allows_execution(self) -> None:
        history = sample_history()
        snapshot = latest_snapshot(
            "spy",
            history,
            compute_macd(history),
            indicator="macd",
            source={"provider": "test"},
        )
        self.assertEqual(snapshot["symbol"], "SPY")
        self.assertFalse(snapshot["execution_allowed"])
        self.assertEqual(snapshot["indicator"], "macd")
        self.assertIn("features", snapshot)


if __name__ == "__main__":
    unittest.main()
