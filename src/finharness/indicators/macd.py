from __future__ import annotations

import numpy as np
import pandas as pd
import talib

from finharness.indicators.shared import validate_ohlcv

MACD_BACKEND = "TA-Lib.MACD"


def compute_macd(
    frame: pd.DataFrame,
    fast_length: int = 12,
    slow_length: int = 26,
    signal_length: int = 9,
) -> pd.DataFrame:
    """Compute MACD, signal, histogram, and display-style states."""
    data = validate_ohlcv(frame)
    close = data["close"].astype(float)
    macd, signal, hist = talib.MACD(
        close,
        fastperiod=fast_length,
        slowperiod=slow_length,
        signalperiod=signal_length,
    )

    output = pd.DataFrame(
        {
            "macd": pd.Series(macd, index=data.index),
            "macd_signal": pd.Series(signal, index=data.index),
            "macd_hist": pd.Series(hist, index=data.index),
        },
        index=data.index,
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
