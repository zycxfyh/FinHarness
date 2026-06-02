from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

REQUIRED_OHLCV = ["date", "open", "high", "low", "close", "volume"]


def validate_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in REQUIRED_OHLCV if column not in frame.columns]
    if missing:
        raise ValueError(f"OHLCV data missing columns: {missing}")
    if frame.empty:
        raise ValueError("OHLCV data is empty")

    normalized = frame[REQUIRED_OHLCV].copy()
    for column in ["open", "high", "low", "close", "volume"]:
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if normalized[["open", "high", "low", "close"]].isna().any().any():
        raise ValueError("OHLC data contains non-numeric values")
    if (normalized[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    return normalized


def latest_snapshot(
    symbol: str,
    frame: pd.DataFrame,
    feature_frame: pd.DataFrame,
    *,
    indicator: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    data = validate_ohlcv(frame)
    latest = data.index[-1]
    return {
        "symbol": symbol.upper(),
        "indicator": indicator,
        "rows": len(data),
        "latest_date": str(data.loc[latest, "date"]),
        "features": clean_values(feature_frame.loc[latest].to_dict()),
        "source": source,
        "execution_allowed": False,
    }


def clean_values(values: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        if pd.isna(value):
            cleaned[key] = None
        elif isinstance(value, np.generic):
            cleaned[key] = value.item()
        else:
            cleaned[key] = value
    return cleaned


def true_range(frame: pd.DataFrame) -> pd.Series:
    data = validate_ohlcv(frame)
    previous_close = data["close"].shift(1)
    ranges = pd.concat(
        [
            data["high"] - data["low"],
            (data["high"] - previous_close).abs(),
            (data["low"] - previous_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)
