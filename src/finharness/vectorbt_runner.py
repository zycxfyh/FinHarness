"""vectorbt research adapter for fast strategy screening."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import vectorbt as vbt

from finharness.indicators.shared import validate_ohlcv
from finharness.research_rigor import (
    return_moments,
    time_train_test_split,
    walk_forward_folds,
)

VECTORBT_BACKEND = "vectorbt.Portfolio.from_signals"


@dataclass(frozen=True)
class VectorbtResearchSummary:
    strategy: str
    backend: str
    start_value: float
    end_value: float
    total_return: float
    trade_count: int
    return_sample_count: int = 0
    observed_sharpe: float | None = None
    return_skew: float | None = None
    return_kurtosis: float | None = None
    psr_gt_zero: float | None = None
    execution_allowed: bool = False


@dataclass(frozen=True)
class VectorbtOosResearchSummary:
    strategy: str
    backend: str
    train_return: float
    test_return: float
    test_trade_count: int
    test_consistent: bool
    test_return_sample_count: int
    test_observed_sharpe: float | None
    test_return_skew: float | None
    test_return_kurtosis: float | None
    test_psr_gt_zero: float | None
    train_rows: int
    test_rows: int
    execution_allowed: bool = False


@dataclass(frozen=True)
class VectorbtWalkForwardFold:
    fold_index: int
    train_rows: int
    test_rows: int
    test_return: float
    test_trade_count: int
    test_observed_sharpe: float | None
    test_psr_gt_zero: float | None


@dataclass(frozen=True)
class VectorbtWalkForwardResearchSummary:
    strategy: str
    backend: str
    folds: tuple[VectorbtWalkForwardFold, ...]
    frac_folds_positive: float
    mean_test_return: float
    mean_test_sharpe: float | None
    fold_count: int
    execution_allowed: bool = False


def run_vectorbt_moving_average_research(
    history: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
    initial_cash: float = 10_000.0,
    fees: float = 0.0,
    slippage: float = 0.0,
) -> VectorbtResearchSummary:
    """Run a vectorized moving-average research screen.

    This is a research adapter, not an execution engine. Signals and portfolio
    statistics are delegated to vectorbt; FinHarness keeps the small summary and
    the no-execution authority boundary.
    """
    return _run_vectorbt_moving_average_research(
        history,
        fast=fast,
        slow=slow,
        initial_cash=initial_cash,
        fees=fees,
        slippage=slippage,
    )[0]


def run_vectorbt_ma_oos(
    history: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
    *,
    train_frac: float = 0.7,
    initial_cash: float = 10_000.0,
    fees: float = 0.0,
    slippage: float = 0.0,
) -> VectorbtOosResearchSummary:
    """Run the fixed MA screen on chronological train/test windows."""
    train_slice, test_slice = time_train_test_split(
        len(history),
        train_frac=train_frac,
        min_train=slow + 1,
        min_test=slow + 1,
    )
    train_history = history.iloc[train_slice].copy()
    test_history = history.iloc[test_slice].copy()
    train_summary = run_vectorbt_moving_average_research(
        train_history,
        fast=fast,
        slow=slow,
        initial_cash=initial_cash,
        fees=fees,
        slippage=slippage,
    )
    test_summary = run_vectorbt_moving_average_research(
        test_history,
        fast=fast,
        slow=slow,
        initial_cash=initial_cash,
        fees=fees,
        slippage=slippage,
    )
    return VectorbtOosResearchSummary(
        strategy=f"vectorbt_ma_oos_{fast}_{slow}",
        backend=VECTORBT_BACKEND,
        train_return=train_summary.total_return,
        test_return=test_summary.total_return,
        test_trade_count=test_summary.trade_count,
        test_consistent=_same_nonzero_sign(
            train_summary.total_return,
            test_summary.total_return,
        ),
        test_return_sample_count=test_summary.return_sample_count,
        test_observed_sharpe=test_summary.observed_sharpe,
        test_return_skew=test_summary.return_skew,
        test_return_kurtosis=test_summary.return_kurtosis,
        test_psr_gt_zero=test_summary.psr_gt_zero,
        train_rows=len(train_history),
        test_rows=len(test_history),
        execution_allowed=False,
    )


def run_vectorbt_ma_walk_forward(
    history: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
    *,
    n_folds: int = 4,
    initial_cash: float = 10_000.0,
    fees: float = 0.0,
    slippage: float = 0.0,
) -> VectorbtWalkForwardResearchSummary:
    """Run the fixed MA screen on expanding-train/forward-test folds."""
    folds = walk_forward_folds(
        len(history),
        n_folds=n_folds,
        min_train=slow + 1,
        min_test=slow + 1,
    )
    fold_summaries: list[VectorbtWalkForwardFold] = []
    for index, (train_slice, test_slice) in enumerate(folds):
        test_history = history.iloc[test_slice].copy()
        test_summary = run_vectorbt_moving_average_research(
            test_history,
            fast=fast,
            slow=slow,
            initial_cash=initial_cash,
            fees=fees,
            slippage=slippage,
        )
        fold_summaries.append(
            VectorbtWalkForwardFold(
                fold_index=index,
                train_rows=(train_slice.stop or 0) - (train_slice.start or 0),
                test_rows=(test_slice.stop or 0) - (test_slice.start or 0),
                test_return=test_summary.total_return,
                test_trade_count=test_summary.trade_count,
                test_observed_sharpe=test_summary.observed_sharpe,
                test_psr_gt_zero=test_summary.psr_gt_zero,
            )
        )

    test_returns = [fold.test_return for fold in fold_summaries]
    positive_count = sum(1 for value in test_returns if value > 0)
    sharpes = [
        fold.test_observed_sharpe
        for fold in fold_summaries
        if fold.test_observed_sharpe is not None and pd.notna(fold.test_observed_sharpe)
    ]
    return VectorbtWalkForwardResearchSummary(
        strategy=f"vectorbt_ma_walk_forward_{fast}_{slow}",
        backend=VECTORBT_BACKEND,
        folds=tuple(fold_summaries),
        frac_folds_positive=positive_count / len(fold_summaries),
        mean_test_return=sum(test_returns) / len(test_returns),
        mean_test_sharpe=(sum(sharpes) / len(sharpes)) if sharpes else None,
        fold_count=len(fold_summaries),
        execution_allowed=False,
    )


def _run_vectorbt_moving_average_research(
    history: pd.DataFrame,
    fast: int,
    slow: int,
    initial_cash: float,
    fees: float,
    slippage: float,
) -> tuple[VectorbtResearchSummary, tuple[float, ...]]:
    if fast <= 0 or slow <= 0:
        raise ValueError("fast and slow windows must be positive")
    if fast >= slow:
        raise ValueError("fast window must be smaller than slow window")
    if len(history) <= slow:
        raise ValueError("history length must be greater than slow window")

    close = _close_series(history)
    fast_ma = vbt.MA.run(close, fast).ma
    slow_ma = vbt.MA.run(close, slow).ma
    entries = fast_ma > slow_ma
    exits = fast_ma < slow_ma

    portfolio = vbt.Portfolio.from_signals(
        close,
        entries,
        exits,
        init_cash=initial_cash,
        fees=fees,
        slippage=slippage,
        freq="1D",
    )
    values = portfolio.value()
    returns = tuple(float(value) for value in portfolio.returns().dropna())
    moments = return_moments(returns)
    return VectorbtResearchSummary(
        strategy=f"vectorbt_ma_research_{fast}_{slow}",
        backend=VECTORBT_BACKEND,
        start_value=float(values.iloc[0]),
        end_value=float(values.iloc[-1]),
        total_return=float(portfolio.total_return()),
        trade_count=int(portfolio.trades.count()),
        return_sample_count=moments.n_samples,
        observed_sharpe=_clean_float(moments.observed_sharpe),
        return_skew=_clean_float(moments.skew),
        return_kurtosis=_clean_float(moments.kurtosis),
        psr_gt_zero=_clean_float(moments.psr_gt_zero),
        execution_allowed=False,
    ), returns


def _close_series(history: pd.DataFrame) -> pd.Series:
    data = validate_ohlcv(history)
    close = data["close"].astype(float).copy()
    close.index = pd.to_datetime(data["date"])
    return close


def _clean_float(value: float) -> float | None:
    return None if pd.isna(value) else float(value)


def _same_nonzero_sign(left: float, right: float) -> bool:
    if left == 0.0 or right == 0.0:
        return False
    return (left > 0.0 and right > 0.0) or (left < 0.0 and right < 0.0)
