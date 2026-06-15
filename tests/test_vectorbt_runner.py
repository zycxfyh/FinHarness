from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

import finharness.vectorbt_runner as vectorbt_runner
from finharness.vectorbt_runner import run_vectorbt_moving_average_research


def sample_history(rows: int = 80) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": f"2026-01-{index % 28 + 1:02d}",
                "open": 100.0 + index * 0.5,
                "high": 101.0 + index * 0.5,
                "low": 99.0 + index * 0.5,
                "close": 100.5 + index * 0.5,
                "volume": 1_000_000 + index,
            }
            for index in range(rows)
        ]
    )


class VectorbtRunnerTest(unittest.TestCase):
    def test_moving_average_research_uses_vectorbt_and_never_authorizes_execution(
        self,
    ) -> None:
        with patch(
            "finharness.vectorbt_runner.vbt.Portfolio.from_signals",
            wraps=vectorbt_runner.vbt.Portfolio.from_signals,
        ) as from_signals:
            summary = run_vectorbt_moving_average_research(sample_history(), fast=5, slow=10)

        self.assertTrue(from_signals.called)
        self.assertEqual(summary.backend, "vectorbt.Portfolio.from_signals")
        self.assertEqual(summary.strategy, "vectorbt_ma_research_5_10")
        self.assertGreater(summary.end_value, 0)
        self.assertFalse(summary.execution_allowed)

    def test_research_rejects_invalid_windows(self) -> None:
        with self.assertRaises(ValueError):
            run_vectorbt_moving_average_research(sample_history(), fast=10, slow=5)


if __name__ == "__main__":
    unittest.main()
