from __future__ import annotations

import math
import unittest

from finharness.research_rigor import (
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    return_moments,
    sharpe_variance,
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

    def test_expected_max_sharpe_grows_with_trials_and_zero_for_single(self) -> None:
        # One trial is no selection, so the deflation benchmark is zero.
        self.assertEqual(expected_max_sharpe(sharpe_variance=0.01, n_trials=1), 0.0)
        # Zero variance across trials -> no inflatable luck -> zero benchmark.
        self.assertEqual(expected_max_sharpe(sharpe_variance=0.0, n_trials=20), 0.0)
        few = expected_max_sharpe(sharpe_variance=0.01, n_trials=5)
        many = expected_max_sharpe(sharpe_variance=0.01, n_trials=100)
        self.assertGreater(few, 0.0)
        self.assertGreater(many, few)  # more trials -> higher bar to clear

    def test_deflated_sharpe_is_psr_for_one_trial_and_lower_for_many(self) -> None:
        kwargs = dict(observed_sharpe=0.15, n_samples=250, skew=0.0, kurtosis=3.0)
        psr = probabilistic_sharpe_ratio(**kwargs)
        # With a single trial DSR reduces to PSR-against-zero.
        dsr_one = deflated_sharpe_ratio(**kwargs, trial_sharpe_variance=0.01, n_trials=1)
        self.assertAlmostEqual(dsr_one, psr)
        # Trying many configs deflates the same result below PSR-against-zero.
        dsr_many = deflated_sharpe_ratio(**kwargs, trial_sharpe_variance=0.01, n_trials=50)
        self.assertLess(dsr_many, psr)
        self.assertGreaterEqual(dsr_many, 0.0)

    def test_sharpe_variance_needs_two_finite_values(self) -> None:
        self.assertEqual(sharpe_variance([1.0]), 0.0)
        self.assertEqual(sharpe_variance([float("nan"), 1.0]), 0.0)
        self.assertGreater(sharpe_variance([0.1, 0.2, 0.3]), 0.0)


if __name__ == "__main__":
    unittest.main()
