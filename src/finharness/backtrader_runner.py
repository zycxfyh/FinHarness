"""Backtrader integration layer."""

from __future__ import annotations

from dataclasses import dataclass

import backtrader as bt
import pandas as pd


@dataclass(frozen=True)
class BacktraderSummary:
    strategy: str
    start_value: float
    end_value: float
    total_return: float


def run_moving_average_backtest(
    history: pd.DataFrame,
    fast: int = 20,
    slow: int = 50,
    initial_cash: float = 10_000.0,
) -> BacktraderSummary:
    """Run a simple moving-average strategy against normalized OHLCV data."""
    if len(history) <= slow:
        raise ValueError("history length must be greater than slow window")

    feed_frame = history.copy()
    feed_frame["date"] = pd.to_datetime(feed_frame["date"])
    feed_frame = feed_frame.set_index("date")

    cerebro = bt.Cerebro()
    cerebro.broker.setcash(initial_cash)
    cerebro.addstrategy(bt.strategies.MA_CrossOver, fast=fast, slow=slow)
    cerebro.adddata(bt.feeds.PandasData(dataname=feed_frame))

    start_value = float(cerebro.broker.getvalue())
    cerebro.run()
    end_value = float(cerebro.broker.getvalue())

    return BacktraderSummary(
        strategy=f"backtrader_ma_hold_{fast}_{slow}",
        start_value=start_value,
        end_value=end_value,
        total_return=end_value / start_value - 1,
    )
