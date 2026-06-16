from __future__ import annotations

import math
import unittest

from finharness.research_rigor import (
    probabilistic_sharpe_ratio,
    return_moments,
    time_train_test_split,
    walk_forward_folds,
)


class ResearchRigorTest(unittest.TestCase):
    def test_time_train_test_split_is_chronological_and_respects_minimums(self) -> None:
        train, test = time_train_test_split(100, train_frac=0.7, min_train=20, min_test=10)

        self.assertEqual((train.start, train.stop), (0, 70))
        self.assertEqual((test.start, test.stop), (70, 100))

    def test_walk_forward_folds_expand_train_and_move_test_forward(self) -> None:
        folds = walk_forward_folds(100, n_folds=4, min_train=20, min_test=20)

        self.assertEqual(len(folds), 4)
        previous_train_stop = 0
        for train, test in folds:
            self.assertEqual(train.start, 0)
            self.assertGreater(train.stop or 0, previous_train_stop)
            self.assertEqual(train.stop, test.start)
            self.assertGreaterEqual((test.stop or 0) - (test.start or 0), 20)
            previous_train_stop = train.stop or 0

    def test_probabilistic_sharpe_ratio_has_expected_shape(self) -> None:
        neutral = probabilistic_sharpe_ratio(
            observed_sharpe=0.0,
            n_samples=50,
            skew=0.0,
            kurtosis=3.0,
        )
        positive = probabilistic_sharpe_ratio(
            observed_sharpe=1.0,
            n_samples=250,
            skew=0.0,
            kurtosis=3.0,
        )
        too_short = probabilistic_sharpe_ratio(
            observed_sharpe=1.0,
            n_samples=1,
            skew=0.0,
            kurtosis=3.0,
        )

        self.assertAlmostEqual(neutral, 0.5)
        self.assertGreater(positive, 0.99)
        self.assertTrue(math.isnan(too_short))

    def test_return_moments_records_psr_without_annualizing(self) -> None:
        moments = return_moments([0.01, -0.01, 0.02, -0.005, 0.015])

        self.assertEqual(moments.n_samples, 5)
        self.assertTrue(math.isfinite(moments.observed_sharpe))
        self.assertTrue(math.isfinite(moments.skew))
        self.assertTrue(math.isfinite(moments.kurtosis))
        self.assertGreaterEqual(moments.psr_gt_zero, 0.0)
        self.assertLessEqual(moments.psr_gt_zero, 1.0)


if __name__ == "__main__":
    unittest.main()
