from __future__ import annotations

import math

import numpy as np
import pandas as pd

from finharness.indicators.shared import true_range, validate_ohlcv


def compute_squeeze_momentum(
    frame: pd.DataFrame,
    bb_length: int = 20,
    bb_mult: float = 2.0,
    kc_length: int = 20,
    kc_mult: float = 1.5,
    use_true_range: bool = True,
) -> pd.DataFrame:
    """Compute a LazyBear-style squeeze momentum feature set."""
    data = validate_ohlcv(frame)
    close = data["close"]

    basis = close.rolling(bb_length, min_periods=bb_length).mean()
    deviation = bb_mult * close.rolling(bb_length, min_periods=bb_length).std()
    upper_bb = basis + deviation
    lower_bb = basis - deviation

    ma = close.rolling(kc_length, min_periods=kc_length).mean()
    price_range = true_range(data) if use_true_range else data["high"] - data["low"]
    range_ma = price_range.rolling(kc_length, min_periods=kc_length).mean()
    upper_kc = ma + range_ma * kc_mult
    lower_kc = ma - range_ma * kc_mult

    highest_high = data["high"].rolling(kc_length, min_periods=kc_length).max()
    lowest_low = data["low"].rolling(kc_length, min_periods=kc_length).min()
    middle = ((highest_high + lowest_low) / 2 + ma) / 2
    momentum = _rolling_linreg_current(close - middle, kc_length)

    squeeze_on = (lower_bb > lower_kc) & (upper_bb < upper_kc)
    squeeze_off = (lower_bb < lower_kc) & (upper_bb > upper_kc)
    no_squeeze = ~squeeze_on & ~squeeze_off
    previous_momentum = momentum.shift(1)

    return pd.DataFrame(
        {
            "squeeze_momentum": momentum,
            "squeeze_state": np.select(
                [squeeze_on, squeeze_off, no_squeeze],
                ["squeeze_on", "squeeze_off", "no_squeeze"],
                default="unknown",
            ),
            "squeeze_momentum_state": np.select(
                [
                    (momentum > 0) & (momentum > previous_momentum),
                    (momentum > 0) & (momentum <= previous_momentum),
                    (momentum <= 0) & (momentum < previous_momentum),
                    (momentum <= 0) & (momentum >= previous_momentum),
                ],
                ["positive_rising", "positive_falling", "negative_falling", "negative_rising"],
                default="unknown",
            ),
        }
    )


def _rolling_linreg_current(values: pd.Series, length: int) -> pd.Series:
    def fit_last(window: np.ndarray) -> float:
        if np.isnan(window).any():
            return math.nan
        x = np.arange(len(window), dtype=float)
        slope, intercept = np.polyfit(x, window, 1)
        return float(slope * (len(window) - 1) + intercept)

    return values.rolling(length, min_periods=length).apply(fit_last, raw=True)
