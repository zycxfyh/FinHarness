from __future__ import annotations

import numpy as np
import pandas as pd
import talib

from finharness.indicators.shared import validate_ohlcv

SQUEEZE_BACKEND = "TA-Lib.BBANDS/TRANGE/SMA/LINEARREG"


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
    close = data["close"].astype(float)
    high = data["high"].astype(float)
    low = data["low"].astype(float)

    upper_bb_raw, _, lower_bb_raw = talib.BBANDS(
        close,
        timeperiod=bb_length,
        nbdevup=bb_mult,
        nbdevdn=bb_mult,
        matype=0,
    )
    upper_bb = pd.Series(upper_bb_raw, index=data.index)
    lower_bb = pd.Series(lower_bb_raw, index=data.index)

    ma = pd.Series(talib.SMA(close, timeperiod=kc_length), index=data.index)
    if use_true_range:
        price_range = pd.Series(talib.TRANGE(high, low, close), index=data.index)
    else:
        price_range = high - low
    range_ma = pd.Series(talib.SMA(price_range, timeperiod=kc_length), index=data.index)
    upper_kc = ma + range_ma * kc_mult
    lower_kc = ma - range_ma * kc_mult

    highest_high = pd.Series(talib.MAX(high, timeperiod=kc_length), index=data.index)
    lowest_low = pd.Series(talib.MIN(low, timeperiod=kc_length), index=data.index)
    middle = ((highest_high + lowest_low) / 2 + ma) / 2
    momentum = pd.Series(
        talib.LINEARREG(close - middle, timeperiod=kc_length),
        index=data.index,
    )

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
