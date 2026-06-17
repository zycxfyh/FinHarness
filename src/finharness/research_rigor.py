"""Research-rigor primitives for rung-limited validation evidence.

These helpers are deliberately pure: they split historical samples and compute
simple return statistics. They do not create proposals, orders, sizing, or
execution permission.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from scipy.stats import norm

ResearchRung = Literal["in_sample", "out_of_sample", "walk_forward", "trial_discounted"]

# Euler-Mascheroni constant, used by the expected-maximum-Sharpe deflation term.
GAMMA_EULER = 0.5772156649015329


@dataclass(frozen=True)
class ReturnMoments:
    """Per-period return moments used by PSR."""

    observed_sharpe: float
    n_samples: int
    skew: float
    kurtosis: float
    psr_gt_zero: float


def standard_normal_cdf(x: float) -> float:
    """Return the standard normal CDF using stdlib math only."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def time_train_test_split(
    n: int,
    train_frac: float = 0.7,
    *,
    min_train: int = 1,
    min_test: int = 1,
) -> tuple[slice, slice]:
    """Return a chronological train/test split."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must be in (0,1)")
    if min_train <= 0 or min_test <= 0:
        raise ValueError("min_train and min_test must be positive")
    if n < min_train + min_test:
        raise ValueError("not enough observations for train/test split")

    cut = int(n * train_frac)
    cut = max(min_train, min(cut, n - min_test))
    return slice(0, cut), slice(cut, n)


def walk_forward_folds(
    n: int,
    n_folds: int = 4,
    *,
    min_train: int = 20,
    min_test: int = 20,
) -> list[tuple[slice, slice]]:
    """Return expanding-train, forward-test folds.

    The function returns as many full test folds as the sample can support, up to
    ``n_folds``. A too-short sample fails fast so callers can degrade to
    not-testable evidence.
    """
    if n <= 0:
        raise ValueError("n must be positive")
    if n_folds <= 0:
        raise ValueError("n_folds must be positive")
    if min_train <= 0 or min_test <= 0:
        raise ValueError("min_train and min_test must be positive")
    if n < min_train + min_test:
        raise ValueError("not enough observations for walk-forward folds")

    available_test = n - min_train
    fold_count = min(n_folds, available_test // min_test)
    if fold_count <= 0:
        raise ValueError("not enough observations for a full test fold")

    test_len = available_test // fold_count
    folds: list[tuple[slice, slice]] = []
    for index in range(fold_count):
        train_end = min_train + index * test_len
        test_end = n if index == fold_count - 1 else train_end + test_len
        if test_end - train_end >= min_test:
            folds.append((slice(0, train_end), slice(train_end, test_end)))
    if not folds:
        raise ValueError("not enough observations for walk-forward folds")
    return folds


def probabilistic_sharpe_ratio(
    *,
    observed_sharpe: float,
    n_samples: int,
    skew: float,
    kurtosis: float,
    benchmark_sharpe: float = 0.0,
) -> float:
    """Probability the true per-period Sharpe exceeds ``benchmark_sharpe``.

    Uses the Bailey/Lopez de Prado PSR approximation. ``kurtosis`` is non-excess
    kurtosis, so a normal distribution is 3.
    """
    if n_samples < 2:
        return float("nan")
    values = [observed_sharpe, skew, kurtosis, benchmark_sharpe]
    if any(not math.isfinite(value) for value in values):
        return float("nan")

    sr = observed_sharpe
    variance_term = 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr
    denom = math.sqrt(max(1e-12, variance_term))
    z_score = (sr - benchmark_sharpe) * math.sqrt(n_samples - 1.0) / denom
    return standard_normal_cdf(z_score)


def expected_max_sharpe(*, sharpe_variance: float, n_trials: int) -> float:
    """Expected maximum Sharpe across ``n_trials`` independent trials under the null.

    This is the deflation benchmark of the Deflated Sharpe Ratio (Bailey & Lopez
    de Prado, 2014): the Sharpe the best of N tried strategies would show by
    chance alone. With one trial there is no selection, so the benchmark is 0.
    """
    if n_trials <= 1 or not math.isfinite(sharpe_variance) or sharpe_variance <= 0.0:
        return 0.0
    std = math.sqrt(sharpe_variance)
    z1 = norm.ppf(1.0 - 1.0 / n_trials)
    z2 = norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(std * ((1.0 - GAMMA_EULER) * z1 + GAMMA_EULER * z2))


def sharpe_variance(sharpes: Sequence[float]) -> float:
    """Sample variance of the trial Sharpe ratios (finite values only)."""
    clean = [float(value) for value in sharpes if math.isfinite(float(value))]
    if len(clean) < 2:
        return 0.0
    return float(statistics.variance(clean))


def deflated_sharpe_ratio(
    *,
    observed_sharpe: float,
    n_samples: int,
    skew: float,
    kurtosis: float,
    trial_sharpe_variance: float,
    n_trials: int,
) -> float:
    """Probability the selected strategy's true Sharpe beats the multiple-testing
    benchmark — the PSR taken against the expected maximum Sharpe of ``n_trials``.

    This is the selection-bias-adjusted statistic the trial_discounted rung needs
    to grant support; PSR-against-zero cannot, because it ignores how many
    configs were tried. Bailey & Lopez de Prado (2014).
    """
    benchmark = expected_max_sharpe(
        sharpe_variance=trial_sharpe_variance, n_trials=n_trials
    )
    if not math.isfinite(benchmark):
        return float("nan")
    return probabilistic_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        n_samples=n_samples,
        skew=skew,
        kurtosis=kurtosis,
        benchmark_sharpe=benchmark,
    )


def return_moments(returns: Iterable[float]) -> ReturnMoments:
    """Compute per-period Sharpe, skew, non-excess kurtosis, and PSR."""
    clean = [float(value) for value in returns if math.isfinite(float(value))]
    n_samples = len(clean)
    if n_samples < 2:
        return ReturnMoments(
            observed_sharpe=float("nan"),
            n_samples=n_samples,
            skew=float("nan"),
            kurtosis=float("nan"),
            psr_gt_zero=float("nan"),
        )

    mean = sum(clean) / n_samples
    centered = [value - mean for value in clean]
    sample_variance = sum(value * value for value in centered) / (n_samples - 1)
    if sample_variance <= 0:
        observed_sharpe = float("nan")
        skew = float("nan")
        kurtosis = float("nan")
    else:
        sample_std = math.sqrt(sample_variance)
        observed_sharpe = mean / sample_std
        population_variance = sum(value * value for value in centered) / n_samples
        population_std = math.sqrt(population_variance)
        skew = sum((value / population_std) ** 3 for value in centered) / n_samples
        kurtosis = sum((value / population_std) ** 4 for value in centered) / n_samples

    psr = probabilistic_sharpe_ratio(
        observed_sharpe=observed_sharpe,
        n_samples=n_samples,
        skew=skew,
        kurtosis=kurtosis,
    )
    return ReturnMoments(
        observed_sharpe=observed_sharpe,
        n_samples=n_samples,
        skew=skew,
        kurtosis=kurtosis,
        psr_gt_zero=psr,
    )
