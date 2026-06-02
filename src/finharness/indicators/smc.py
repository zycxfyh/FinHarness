from __future__ import annotations

import pandas as pd

from finharness.indicators.shared import validate_ohlcv


def compute_smc(
    frame: pd.DataFrame,
    zigzag_len: int = 9,
    fib_factor: float = 0.33,
    order_block_lookback: int = 20,
) -> pd.DataFrame:
    """Compute an MSB/order-block style SMC feature set.

    This is a Python feature implementation inspired by common market-structure
    break and order-block logic. It is not a verbatim copy of proprietary
    TradingView drawing scripts.
    """
    data = validate_ohlcv(frame).reset_index(drop=True)
    highs: list[float] = []
    lows: list[float] = []
    trend = 1
    market = 1
    active_bullish_ob: tuple[float, float] | None = None
    active_bearish_ob: tuple[float, float] | None = None

    records: list[dict[str, object]] = []
    for index, row in data.iterrows():
        lookback = data.iloc[max(0, index - zigzag_len + 1) : index + 1]
        to_up = float(row["high"]) >= float(lookback["high"].max())
        to_down = float(row["low"]) <= float(lookback["low"].min())

        previous_trend = trend
        if trend == 1 and to_down:
            trend = -1
        elif trend == -1 and to_up:
            trend = 1

        if trend != previous_trend:
            if trend == 1:
                lows.append(float(lookback["low"].min()))
            else:
                highs.append(float(lookback["high"].max()))

        h0 = highs[-1] if highs else None
        h1 = highs[-2] if len(highs) >= 2 else None
        l0 = lows[-1] if lows else None
        l1 = lows[-2] if len(lows) >= 2 else None

        msb = "none"
        if (
            h0 is not None
            and h1 is not None
            and l0 is not None
            and market == -1
            and h0 > h1 + abs(h1 - l0) * fib_factor
        ):
            market = 1
            msb = "bullish_msb"
            active_bullish_ob = _last_opposite_candle_zone(
                data, index, order_block_lookback, bearish_candle=True
            )
        if (
            l0 is not None
            and l1 is not None
            and h0 is not None
            and market == 1
            and l0 < l1 - abs(h0 - l1) * fib_factor
        ):
            market = -1
            msb = "bearish_msb"
            active_bearish_ob = _last_opposite_candle_zone(
                data, index, order_block_lookback, bearish_candle=False
            )

        close = float(row["close"])
        if active_bullish_ob is not None and close < active_bullish_ob[1]:
            active_bullish_ob = None
        if active_bearish_ob is not None and close > active_bearish_ob[0]:
            active_bearish_ob = None

        records.append(
            {
                "smc_trend": "up_leg" if trend == 1 else "down_leg",
                "smc_market_bias": "bullish" if market == 1 else "bearish",
                "smc_break": msb,
                "smc_swing_high": h0,
                "smc_previous_swing_high": h1,
                "smc_swing_low": l0,
                "smc_previous_swing_low": l1,
                "smc_bullish_ob_top": active_bullish_ob[0] if active_bullish_ob else None,
                "smc_bullish_ob_bottom": active_bullish_ob[1] if active_bullish_ob else None,
                "smc_bearish_ob_top": active_bearish_ob[0] if active_bearish_ob else None,
                "smc_bearish_ob_bottom": active_bearish_ob[1] if active_bearish_ob else None,
            }
        )

    return pd.DataFrame(records)


def _last_opposite_candle_zone(
    data: pd.DataFrame,
    current_index: int,
    lookback: int,
    *,
    bearish_candle: bool,
) -> tuple[float, float] | None:
    start = max(0, int(current_index) - lookback)
    window = data.iloc[start:int(current_index)]
    for _, row in window.iloc[::-1].iterrows():
        is_bearish = row["open"] > row["close"]
        if is_bearish == bearish_candle:
            return float(row["high"]), float(row["low"])
    return None
