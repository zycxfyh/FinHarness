from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from finharness import data_quality

REQUIRED_OHLCV = data_quality.REQUIRED_OHLCV


def validate_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    return data_quality.validate_ohlcv_strict(frame)


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
