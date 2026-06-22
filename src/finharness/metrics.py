"""Risk-return metrics behind a stable FinHarness summary interface."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

import pandas as pd
import quantstats as qs

TRADING_DAYS = 252
METRICS_BACKEND = "quantstats"


@dataclass(frozen=True)
class RiskReturnSummary:
    total_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    sharpe_ratio: float | None


def pct_returns(prices: list[float]) -> list[float]:
    """Return simple percentage returns from ordered prices."""
    values = _validate_positive_prices(prices, min_count=0)
    if len(values) < 2:
        return []

    return _returns_series(values).tolist()


def max_drawdown(prices: list[float]) -> float:
    """Return max drawdown as a negative fraction."""
    values = _validate_positive_prices(prices, min_count=0)
    if not values:
        return 0.0

    returns = _returns_series(values)
    if returns.empty:
        return 0.0
    return _finite_float(qs.stats.max_drawdown(returns), default=0.0)


def summarize(prices: list[float], risk_free_rate: float = 0.0) -> RiskReturnSummary:
    """Summarize an ordered price series."""
    values = _validate_positive_prices(prices, min_count=2)
    returns = _returns_series(values)
    annualized_volatility = _finite_float(
        qs.stats.volatility(returns, periods=TRADING_DAYS),
        default=0.0,
    )
    sharpe_ratio = (
        None
        if annualized_volatility == 0
        else _nullable_float(qs.stats.sharpe(returns, rf=risk_free_rate, periods=TRADING_DAYS))
    )

    return RiskReturnSummary(
        total_return=_finite_float(qs.stats.comp(returns), default=0.0),
        annualized_return=_finite_float(qs.stats.cagr(returns, periods=TRADING_DAYS), default=0.0),
        annualized_volatility=annualized_volatility,
        max_drawdown=max_drawdown(values),
        sharpe_ratio=sharpe_ratio,
    )


def _validate_positive_prices(prices: list[float], *, min_count: int) -> list[float]:
    if len(prices) < min_count:
        raise ValueError("need at least two prices")
    values = [float(price) for price in prices]
    if any(price <= 0 for price in values):
        raise ValueError("prices must be positive")
    return values


def _returns_series(prices: list[float]) -> pd.Series:
    return pd.Series(prices, dtype="float64").pct_change().dropna()


def _finite_float(value: Any, *, default: float) -> float:
    result = float(value)
    return result if isfinite(result) else default


def _nullable_float(value: Any) -> float | None:
    result = float(value)
    return result if isfinite(result) else None
