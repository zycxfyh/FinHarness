from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

import finharness.vectorbt_runner as vectorbt_runner
from finharness.vectorbt_runner import (
    run_vectorbt_ma_oos,
    run_vectorbt_ma_walk_forward,
    run_vectorbt_moving_average_research,
)


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

    def test_oos_research_uses_vectorbt_sub_windows_and_never_authorizes_execution(
        self,
    ) -> None:
        with patch(
            "finharness.vectorbt_runner.vbt.Portfolio.from_signals",
            wraps=vectorbt_runner.vbt.Portfolio.from_signals,
        ) as from_signals:
            summary = run_vectorbt_ma_oos(sample_history(rows=90), fast=5, slow=10)

        self.assertGreaterEqual(from_signals.call_count, 2)
        self.assertEqual(summary.backend, "vectorbt.Portfolio.from_signals")
        self.assertGreater(summary.train_rows, summary.test_rows)
        self.assertGreaterEqual(summary.test_rows, 11)
        self.assertIsNotNone(summary.test_psr_gt_zero)
        self.assertFalse(summary.execution_allowed)

    def test_walk_forward_research_uses_forward_test_folds_and_never_authorizes_execution(
        self,
    ) -> None:
        with patch(
            "finharness.vectorbt_runner.vbt.Portfolio.from_signals",
            wraps=vectorbt_runner.vbt.Portfolio.from_signals,
        ) as from_signals:
            summary = run_vectorbt_ma_walk_forward(
                sample_history(rows=90),
                fast=5,
                slow=10,
                n_folds=3,
            )

        self.assertEqual(summary.fold_count, 3)
        self.assertEqual(from_signals.call_count, 3)
        self.assertGreaterEqual(summary.frac_folds_positive, 0.0)
        self.assertLessEqual(summary.frac_folds_positive, 1.0)
        self.assertTrue(all(fold.test_rows >= 11 for fold in summary.folds))
        self.assertFalse(summary.execution_allowed)


if __name__ == "__main__":
    unittest.main()
