"""OHLCV data-quality contract backed by Pandera.

Pandera owns structural mechanics: dtype, nullability, and price positivity.
FinHarness keeps verdict semantics: duplicate counts, null counts, freshness,
receipts, and the no-execution authority boundary.
"""

from __future__ import annotations

from importlib import metadata

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

REQUIRED_OHLCV = ["date", "open", "high", "low", "close", "volume"]
OHLCV_NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume")
OHLC_PRICE_COLUMNS = ("open", "high", "low", "close")
DATA_QUALITY_BACKEND = "pandera"

OHLCV_STRICT_SCHEMA = pa.DataFrameSchema(
    {
        "date": pa.Column(nullable=True, required=True, coerce=False),
        "open": pa.Column(float, pa.Check.gt(0), nullable=False, required=True),
        "high": pa.Column(float, pa.Check.gt(0), nullable=False, required=True),
        "low": pa.Column(float, pa.Check.gt(0), nullable=False, required=True),
        "close": pa.Column(float, pa.Check.gt(0), nullable=False, required=True),
        "volume": pa.Column(float, nullable=True, required=True, coerce=True),
    },
    strict=False,
    ordered=False,
)

_POSITIVITY_SCHEMA = pa.DataFrameSchema(
    {
        column: pa.Column(float, pa.Check.gt(0), nullable=True, required=False)
        for column in OHLC_PRICE_COLUMNS
    },
    strict=False,
    ordered=False,
)


def data_quality_backend_version() -> str | None:
    try:
        return metadata.version(DATA_QUALITY_BACKEND)
    except metadata.PackageNotFoundError:
        return None


def validate_ohlcv_strict(frame: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize OHLCV data while preserving legacy errors."""

    missing = [column for column in REQUIRED_OHLCV if column not in frame.columns]
    if missing:
        raise ValueError(f"OHLCV data missing columns: {missing}")
    if frame.empty:
        raise ValueError("OHLCV data is empty")

    working = frame[REQUIRED_OHLCV].copy()
    for column in OHLCV_NUMERIC_COLUMNS:
        working[column] = pd.to_numeric(working[column], errors="coerce").astype(float)

    if working[list(OHLC_PRICE_COLUMNS)].isna().any().any():
        raise ValueError("OHLC data contains non-numeric values")

    try:
        return OHLCV_STRICT_SCHEMA.validate(working, lazy=True)
    except SchemaErrors as exc:
        raise ValueError("OHLC prices must be positive") from exc


def price_outlier_flags(numeric_ohlc: pd.DataFrame) -> list[str]:
    """Return soft-path outlier flags from the shared positivity contract.

    Missing prices are recorded by MarketDataQuality.null_counts; they are not
    non-positive price outliers.
    """

    present = [column for column in OHLC_PRICE_COLUMNS if column in numeric_ohlc.columns]
    flags: list[str] = []
    working = numeric_ohlc[present].astype(float) if present else pd.DataFrame()
    if present:
        try:
            _POSITIVITY_SCHEMA.validate(working, lazy=True)
        except SchemaErrors as exc:
            bad_columns = set(exc.failure_cases["column"].astype(str))
            flags.extend(
                f"{column}_non_positive" for column in present if column in bad_columns
            )

    if {"high", "low"}.issubset(working.columns) and (
        working["high"] < working["low"]
    ).any():
        flags.append("high_below_low")
    return flags
