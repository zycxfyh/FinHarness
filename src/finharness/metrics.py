"""Small finance metrics used before heavier wheels are installed."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import stdev

TRADING_DAYS = 252


@dataclass(frozen=True)
class RiskReturnSummary:
    total_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    sharpe_ratio: float | None


def pct_returns(prices: list[float]) -> list[float]:
    """Return simple percentage returns from ordered prices."""
    if len(prices) < 2:
        return []

    returns: list[float] = []
    for previous, current in zip(prices, prices[1:], strict=False):
        if previous <= 0:
            raise ValueError("prices must be positive")
        returns.append(current / previous - 1)
    return returns


def max_drawdown(prices: list[float]) -> float:
    """Return max drawdown as a negative fraction."""
    if not prices:
        return 0.0

    peak = prices[0]
    worst = 0.0
    for price in prices:
        if price <= 0:
            raise ValueError("prices must be positive")
        peak = max(peak, price)
        drawdown = price / peak - 1
        worst = min(worst, drawdown)
    return worst


def summarize(prices: list[float], risk_free_rate: float = 0.0) -> RiskReturnSummary:
    """Summarize an ordered price series."""
    if len(prices) < 2:
        raise ValueError("need at least two prices")
    if any(price <= 0 for price in prices):
        raise ValueError("prices must be positive")

    returns = pct_returns(prices)
    total_return = prices[-1] / prices[0] - 1
    years = len(returns) / TRADING_DAYS
    annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0.0
    annualized_volatility = stdev(returns) * math.sqrt(TRADING_DAYS) if len(returns) > 1 else 0.0

    if annualized_volatility == 0:
        sharpe_ratio = None
    else:
        sharpe_ratio = (annualized_return - risk_free_rate) / annualized_volatility

    return RiskReturnSummary(
        total_return=total_return,
        annualized_return=annualized_return,
        annualized_volatility=annualized_volatility,
        max_drawdown=max_drawdown(prices),
        sharpe_ratio=sharpe_ratio,
    )
