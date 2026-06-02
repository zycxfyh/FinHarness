"""Second-layer indicator governance over first-layer market data.

The indicator library owns indicator math. FinHarness owns the evidence model,
quality report, lineage, and execution boundary.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
import pandas_ta as ta
import talib
from pydantic import BaseModel, ConfigDict, Field

from finharness.indicators.shared import validate_ohlcv
from finharness.market_data import (
    ROOT,
    MarketDataSnapshot,
    display_path,
    package_version,
    sha256_text,
)

INDICATOR_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "indicators"
INDICATOR_RECEIPT_ROOT = ROOT / "data" / "receipts" / "indicators"
TRADING_DAYS = 252


class IndicatorSpec(BaseModel):
    """Indicator request owned by a mature indicator library."""

    model_config = ConfigDict(frozen=True)

    name: str
    library: str
    library_version: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class IndicatorQuality(BaseModel):
    """Quality report for an indicator feature frame."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    row_count: int
    feature_count: int
    warmup_null_counts: dict[str, int] = Field(default_factory=dict)
    latest_null_features: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class IndicatorLineage(BaseModel):
    """Lineage from first-layer market-data snapshot into indicator output."""

    model_config = ConfigDict(frozen=True)

    input_snapshot_id: str | None
    input_payload_ref: str | None
    indicator_specs: list[IndicatorSpec]
    computed_at_utc: str
    transform_version: str = "finharness.indicator_layer.v1"
    output_hash: str
    output_ref: str


class IndicatorSnapshot(BaseModel):
    """Feature snapshot consumed by research, risk, and reporting."""

    model_config = ConfigDict(frozen=True)

    indicator_snapshot_id: str
    symbol: str
    as_of_utc: str
    latest_date: str
    features: dict[str, Any]
    quality: IndicatorQuality
    lineage: IndicatorLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False


class IndicatorReceipt(BaseModel):
    """Durable evidence root for second-layer indicator processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "indicator_processing"
    stage_flow: dict[str, str]
    snapshot: IndicatorSnapshot


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def clean_feature_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def clean_feature_row(row: pd.Series) -> dict[str, Any]:
    return {key: clean_feature_value(value) for key, value in row.to_dict().items()}


def compute_library_core_indicators(
    history: pd.DataFrame,
    *,
    ma_fast: int = 20,
    ma_slow: int = 50,
    rsi_window: int = 14,
    bb_window: int = 20,
    bb_alpha: float = 2.0,
) -> tuple[pd.DataFrame, list[IndicatorSpec]]:
    """Compute core indicators with TA-Lib and pandas-ta instead of local math."""
    data = validate_ohlcv(history)
    close = data["close"].astype(float)
    high = data["high"].astype(float)
    low = data["low"].astype(float)

    fast_ma = pd.Series(talib.SMA(close, timeperiod=ma_fast), index=data.index)
    slow_ma = pd.Series(talib.SMA(close, timeperiod=ma_slow), index=data.index)
    macd, macd_signal, macd_hist = talib.MACD(close)
    rsi = pd.Series(talib.RSI(close, timeperiod=rsi_window), index=data.index)
    bb_upper, bb_middle, bb_lower = talib.BBANDS(
        close,
        timeperiod=bb_window,
        nbdevup=bb_alpha,
        nbdevdn=bb_alpha,
    )
    atr = ta.atr(high=high, low=low, close=close, length=14)

    technical_frame = pd.DataFrame(
        {
            "ma_fast": fast_ma,
            "ma_slow": slow_ma,
            "ma_trend": np.where(fast_ma >= slow_ma, "bullish", "bearish"),
            "macd": macd,
            "macd_signal": macd_signal,
            "macd_hist": macd_hist,
            "macd_bias": np.where(macd >= macd_signal, "bullish", "bearish"),
            "rsi": rsi,
            "rsi_state": np.select(
                [rsi >= 70, rsi <= 30],
                ["overbought", "oversold"],
                default="neutral",
            ),
            "bb_middle": bb_middle,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_percent_b": (close - bb_lower) / (bb_upper - bb_lower),
            "bb_bandwidth": (bb_upper - bb_lower) / bb_middle,
            "atr": atr,
        }
    )
    risk_frame = compute_ohlcv_risk_return_features(data)
    frame = pd.concat([technical_frame, risk_frame], axis=1)
    specs = [
        IndicatorSpec(
            name="TA-Lib.SMA.fast",
            library="TA-Lib",
            library_version=package_version("ta-lib"),
            params={"window": ma_fast},
        ),
        IndicatorSpec(
            name="TA-Lib.SMA.slow",
            library="TA-Lib",
            library_version=package_version("ta-lib"),
            params={"window": ma_slow},
        ),
        IndicatorSpec(
            name="TA-Lib.MACD",
            library="TA-Lib",
            library_version=package_version("ta-lib"),
            params={},
        ),
        IndicatorSpec(
            name="TA-Lib.RSI",
            library="TA-Lib",
            library_version=package_version("ta-lib"),
            params={"window": rsi_window},
        ),
        IndicatorSpec(
            name="TA-Lib.BBANDS",
            library="TA-Lib",
            library_version=package_version("ta-lib"),
            params={"window": bb_window, "alpha": bb_alpha},
        ),
        IndicatorSpec(
            name="pandas-ta.ATR",
            library="pandas-ta",
            library_version=package_version("pandas-ta"),
            params={"length": 14},
        ),
        IndicatorSpec(
            name="FinHarness.OHLCV.risk_return_features",
            library="pandas/numpy",
            library_version=f"pandas={package_version('pandas')};numpy={package_version('numpy')}",
            params={
                "return_basis": "close",
                "annualization_days": TRADING_DAYS,
                "rolling_window": 20,
                "var_confidence": 0.95,
            },
        ),
    ]
    return frame, specs


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    result = numerator / denominator.replace(0, np.nan)
    return result.replace([np.inf, -np.inf], np.nan)


def _annualized_return_from_total(total_return: pd.Series, periods: pd.Series) -> pd.Series:
    years = periods / TRADING_DAYS
    result = pd.Series(np.nan, index=total_return.index, dtype=float)
    valid = years > 0
    result.loc[valid] = (1.0 + total_return.loc[valid]).pow(1.0 / years.loc[valid]) - 1.0
    return result


def _rolling_cvar(returns: pd.Series, *, window: int, confidence: float) -> pd.Series:
    tail_probability = 1.0 - confidence

    def calculate(values: np.ndarray) -> float:
        clean = values[~np.isnan(values)]
        if len(clean) == 0:
            return math.nan
        threshold = np.quantile(clean, tail_probability)
        tail = clean[clean <= threshold]
        if len(tail) == 0:
            return math.nan
        return float(tail.mean())

    return returns.rolling(window=window, min_periods=window).apply(calculate, raw=True)


def _drawdown_duration(drawdown: pd.Series) -> pd.Series:
    duration = []
    current = 0
    for value in drawdown.fillna(0.0):
        if value < 0:
            current += 1
        else:
            current = 0
        duration.append(current)
    return pd.Series(duration, index=drawdown.index, dtype=float)


def compute_ohlcv_risk_return_features(
    history: pd.DataFrame,
    *,
    rolling_window: int = 20,
    annualization_days: int = TRADING_DAYS,
    var_confidence: float = 0.95,
) -> pd.DataFrame:
    """Compute OHLCV-derived risk/return formula features.

    These are descriptive evidence features only. They do not validate a
    trading edge and do not authorize sizing or execution.
    """
    data = validate_ohlcv(history)
    close = data["close"].astype(float)
    simple_return = close.pct_change()
    log_return = np.log(close / close.shift(1))
    wealth_index = close / close.iloc[0]
    cumulative_return = wealth_index - 1.0
    cumulative_log_return = log_return.fillna(0.0).cumsum()
    running_peak = wealth_index.cummax()
    drawdown = wealth_index / running_peak - 1.0
    max_drawdown_to_date = drawdown.cummin()
    drawdown_duration = _drawdown_duration(drawdown)
    periods = pd.Series(range(len(close)), index=close.index, dtype=float)

    rolling_mean = simple_return.rolling(
        window=rolling_window,
        min_periods=rolling_window,
    ).mean()
    rolling_vol = simple_return.rolling(
        window=rolling_window,
        min_periods=rolling_window,
    ).std()
    expanding_mean = simple_return.expanding(min_periods=2).mean()
    expanding_vol = simple_return.expanding(min_periods=2).std()
    annualized_return = _annualized_return_from_total(cumulative_return, periods)
    annualized_volatility = expanding_vol * math.sqrt(annualization_days)
    expanding_sharpe = _safe_divide(annualized_return, annualized_volatility)
    rolling_var = simple_return.rolling(
        window=rolling_window,
        min_periods=rolling_window,
    ).quantile(1.0 - var_confidence)
    rolling_cvar = _rolling_cvar(
        simple_return,
        window=rolling_window,
        confidence=var_confidence,
    )

    return pd.DataFrame(
        {
            "simple_return": simple_return,
            "log_return": log_return,
            "wealth_index": wealth_index,
            "cumulative_return": cumulative_return,
            "cumulative_log_return": cumulative_log_return,
            "drawdown": drawdown,
            "max_drawdown_to_date": max_drawdown_to_date,
            "drawdown_duration": drawdown_duration,
            "rolling_mean_return_20d": rolling_mean,
            "rolling_volatility_20d_annualized": rolling_vol * math.sqrt(annualization_days),
            "expanding_mean_return_annualized": expanding_mean * annualization_days,
            "expanding_return_annualized": annualized_return,
            "expanding_volatility_annualized": annualized_volatility,
            "expanding_sharpe": expanding_sharpe,
            "rolling_var_95_20d": rolling_var,
            "rolling_cvar_95_20d": rolling_cvar,
            "rolling_skew_20d": simple_return.rolling(
                window=rolling_window,
                min_periods=rolling_window,
            ).skew(),
            "rolling_kurtosis_20d": simple_return.rolling(
                window=rolling_window,
                min_periods=rolling_window,
            ).kurt(),
        },
        index=data.index,
    )


def build_indicator_quality(feature_frame: pd.DataFrame) -> IndicatorQuality:
    latest = feature_frame.iloc[-1]
    latest_null_features = [column for column in feature_frame.columns if pd.isna(latest[column])]
    warmup_null_counts = {
        column: int(feature_frame[column].isna().sum())
        for column in feature_frame.columns
        if int(feature_frame[column].isna().sum()) > 0
    }
    numeric = feature_frame.select_dtypes(include=["number"])
    has_infinite = bool(np.isinf(numeric.to_numpy()).any()) if not numeric.empty else False
    notes = ["latest row has warmup nulls"] if latest_null_features else []
    if has_infinite:
        notes.append("numeric features contain infinite values")
    return IndicatorQuality(
        ok=not latest_null_features and not has_infinite,
        row_count=len(feature_frame),
        feature_count=len(feature_frame.columns),
        warmup_null_counts=warmup_null_counts,
        latest_null_features=latest_null_features,
        notes=notes,
    )


def write_indicator_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    )


def build_indicator_snapshot(
    *,
    symbol: str,
    history: pd.DataFrame,
    market_data_snapshot: MarketDataSnapshot | None = None,
    ma_fast: int = 20,
    ma_slow: int = 50,
    feature_frame: pd.DataFrame | None = None,
    indicator_specs: list[IndicatorSpec] | None = None,
) -> IndicatorReceipt:
    data = validate_ohlcv(history)
    if feature_frame is None or indicator_specs is None:
        feature_frame, specs = compute_library_core_indicators(
            data,
            ma_fast=ma_fast,
            ma_slow=ma_slow,
        )
    else:
        specs = indicator_specs
    quality = build_indicator_quality(feature_frame)

    snapshot_id = f"inds_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    receipt_id = f"receipt_{snapshot_id}"
    output_ref = INDICATOR_NORMALIZED_ROOT / f"{snapshot_id}.json"
    receipt_ref = INDICATOR_RECEIPT_ROOT / f"{receipt_id}.json"
    latest_index = data.index[-1]
    latest_date = str(data.loc[latest_index, "date"])
    latest_features = clean_feature_row(feature_frame.loc[latest_index])
    output_payload = {
        "symbol": symbol.upper(),
        "latest_date": latest_date,
        "features": latest_features,
        "records": feature_frame.to_dict(orient="records"),
    }

    lineage = IndicatorLineage(
        input_snapshot_id=market_data_snapshot.snapshot_id if market_data_snapshot else None,
        input_payload_ref=market_data_snapshot.payload_ref if market_data_snapshot else None,
        indicator_specs=specs,
        computed_at_utc=now_utc(),
        output_hash=sha256_text(json.dumps(output_payload, sort_keys=True, default=str)),
        output_ref=display_path(output_ref),
    )
    snapshot = IndicatorSnapshot(
        indicator_snapshot_id=snapshot_id,
        symbol=symbol.upper(),
        as_of_utc=now_utc(),
        latest_date=latest_date,
        features=latest_features,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(output_ref),
        receipt_ref=display_path(receipt_ref),
    )
    receipt = IndicatorReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "initiation": "core indicator layer over first-layer MarketDataSnapshot",
            "planning": "library-owned indicator math, FinHarness-owned governance",
            "preparation": "TA-Lib and pandas-ta installed as indicator libraries",
            "execution": (
                "compute TA-Lib SMA/MACD/RSI/BBANDS, pandas-ta ATR, and OHLCV "
                "risk/return formula features"
            ),
            "monitoring": "IndicatorQuality flags warmup/latest nulls and infinities",
            "closing": "IndicatorSnapshot + IndicatorReceipt written",
            "documentation": "docs/notes/indicator-layer-execution.md",
            "retrospective": "keep custom indicators experimental until library-backed",
        },
        snapshot=snapshot,
    )

    write_indicator_json(output_ref, output_payload)
    write_indicator_json(receipt_ref, receipt.model_dump(mode="json"))
    return receipt
