from __future__ import annotations

import numpy as np
import pandas as pd

from finharness.indicators.shared import validate_ohlcv


def compute_macd(
    frame: pd.DataFrame,
    fast_length: int = 12,
    slow_length: int = 26,
    signal_length: int = 9,
) -> pd.DataFrame:
    """Compute MACD, signal, histogram, and display-style states."""
    data = validate_ohlcv(frame)
    close = data["close"]

    fast_ma = close.ewm(span=fast_length, adjust=False).mean()
    slow_ma = close.ewm(span=slow_length, adjust=False).mean()
    macd = fast_ma - slow_ma
    signal = macd.rolling(signal_length, min_periods=signal_length).mean()
    hist = macd - signal

    output = pd.DataFrame(
        {
            "macd": macd,
            "macd_signal": signal,
            "macd_hist": hist,
        }
    )
    previous_hist = output["macd_hist"].shift(1)
    output["macd_hist_state"] = np.select(
        [
            (output["macd_hist"] > previous_hist) & (output["macd_hist"] > 0),
            (output["macd_hist"] < previous_hist) & (output["macd_hist"] > 0),
            (output["macd_hist"] < previous_hist) & (output["macd_hist"] <= 0),
            (output["macd_hist"] > previous_hist) & (output["macd_hist"] <= 0),
        ],
        ["positive_rising", "positive_falling", "negative_falling", "negative_rising"],
        default="unknown",
    )
    output["macd_bias"] = np.where(output["macd"] >= output["macd_signal"], "bullish", "bearish")
    output["macd_cross"] = np.where(
        (output["macd"].shift(1) < output["macd_signal"].shift(1))
        & (output["macd"] >= output["macd_signal"]),
        "bullish_cross",
        np.where(
            (output["macd"].shift(1) >= output["macd_signal"].shift(1))
            & (output["macd"] < output["macd_signal"]),
            "bearish_cross",
            "none",
        ),
    )
    return output
