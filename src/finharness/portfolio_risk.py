"""Riskfolio-Lib adapter for portfolio risk research."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import riskfolio as rp

RISKFOLIO_BACKEND = "Riskfolio-Lib.Portfolio.optimization"


@dataclass(frozen=True)
class RiskfolioAllocationSummary:
    backend: str
    model: str
    risk_measure: str
    objective: str
    weights: dict[str, float]
    weight_sum: float
    max_weight: float
    concentration_cap: float | None
    concentration_ok: bool | None
    execution_allowed: bool = False


def concentration_request_from_allocation(
    summary: RiskfolioAllocationSummary, symbol: str
) -> float:
    """Return a per-symbol concentration REQUEST from Riskfolio evidence.

    This value is an input for risk-gate review. It is never a mandate cap and
    never authority to exceed one.
    """

    return float(summary.weights.get(symbol.upper(), 0.0))


def optimize_riskfolio_allocation(
    returns: pd.DataFrame,
    *,
    model: str = "Classic",
    risk_measure: str = "MV",
    objective: str = "Sharpe",
    concentration_cap: float | None = None,
    risk_free_rate: float = 0.0,
) -> RiskfolioAllocationSummary:
    """Optimize research allocation weights with Riskfolio-Lib.

    This adapter deliberately returns a research summary only. Riskfolio owns the
    optimizer; FinHarness keeps concentration reporting and the no-execution
    authority boundary.
    """
    clean_returns = _validate_returns(returns)
    if concentration_cap is not None:
        _validate_concentration_cap(concentration_cap, asset_count=len(clean_returns.columns))

    portfolio = rp.Portfolio(
        returns=clean_returns,
        upperlng=concentration_cap if concentration_cap is not None else 1,
    )
    portfolio.assets_stats(method_mu="hist", method_cov="hist")
    raw_weights = portfolio.optimization(
        model=model,
        rm=risk_measure,
        obj=objective,
        rf=risk_free_rate,
        hist=True,
    )
    if raw_weights is None or raw_weights.empty:
        raise RuntimeError("Riskfolio-Lib returned no allocation weights")

    weights = _weights_dict(raw_weights)
    max_weight = max(weights.values())
    concentration_ok = (
        None if concentration_cap is None else max_weight <= concentration_cap + 1e-8
    )
    return RiskfolioAllocationSummary(
        backend=RISKFOLIO_BACKEND,
        model=model,
        risk_measure=risk_measure,
        objective=objective,
        weights=weights,
        weight_sum=sum(weights.values()),
        max_weight=max_weight,
        concentration_cap=concentration_cap,
        concentration_ok=concentration_ok,
        execution_allowed=False,
    )


def returns_from_close_prices(close_prices: pd.DataFrame) -> pd.DataFrame:
    """Build a numeric returns matrix from close prices."""
    if close_prices.empty:
        raise ValueError("close price matrix is empty")
    numeric = close_prices.apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise ValueError("close price matrix contains non-numeric values")
    if (numeric <= 0).any().any():
        raise ValueError("close prices must be positive")
    return numeric.pct_change().dropna(how="any")


def _validate_returns(returns: pd.DataFrame) -> pd.DataFrame:
    if returns.empty:
        raise ValueError("returns matrix is empty")
    if len(returns.columns) < 2:
        raise ValueError("returns matrix must contain at least two assets")
    numeric = returns.apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise ValueError("returns matrix contains non-numeric or missing values")
    return numeric


def _validate_concentration_cap(cap: float, *, asset_count: int) -> None:
    if cap <= 0 or cap > 1:
        raise ValueError("concentration cap must be in (0, 1]")
    if cap * asset_count < 1:
        raise ValueError("concentration cap is infeasible for the asset count")


def _weights_dict(raw_weights: pd.DataFrame) -> dict[str, float]:
    if "weights" not in raw_weights.columns:
        raise RuntimeError("Riskfolio-Lib weights output missing 'weights' column")
    return {
        str(symbol).upper(): float(weight)
        for symbol, weight in raw_weights["weights"].items()
    }
