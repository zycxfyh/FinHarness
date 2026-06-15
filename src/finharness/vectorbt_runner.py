"""vectorbt research adapter for fast strategy screening."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import vectorbt as vbt

from finharness.indicators.shared import validate_ohlcv

VECTORBT_BACKEND = "vectorbt.Portfolio.from_signals"


@dataclass(frozen=True)
class VectorbtResearchSummary:
    strategy: str
    backend: str
    start_value: float
    end_value: float
    total_return: float
    trade_count: int
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
    return VectorbtResearchSummary(
        strategy=f"vectorbt_ma_research_{fast}_{slow}",
        backend=VECTORBT_BACKEND,
        start_value=float(values.iloc[0]),
        end_value=float(values.iloc[-1]),
        total_return=float(portfolio.total_return()),
        trade_count=int(portfolio.trades.count()),
        execution_allowed=False,
    )


def _close_series(history: pd.DataFrame) -> pd.Series:
    data = validate_ohlcv(history)
    close = data["close"].astype(float).copy()
    close.index = pd.to_datetime(data["date"])
    return close
