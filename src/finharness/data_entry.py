"""Data entry layer built on top community wheels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Any, Literal

import pandas as pd
import yfinance as yf


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    name: str | None
    exchange: str | None
    last_price: float | None
    previous_close: float | None
    currency: str | None
    provider: str


class OptionalProviderUnavailable(RuntimeError):
    """Raised when an optional market-data provider is not installed."""


def _openbb_app() -> Any:
    try:
        from openbb import obb
    except (ImportError, ModuleNotFoundError) as exc:
        raise OptionalProviderUnavailable(
            "OpenBB is optional and is not installed in the default hardened environment"
        ) from exc
    return obb


def fetch_openbb_quote(symbol: str) -> QuoteSnapshot:
    """Fetch a current quote through OpenBB's yfinance provider when installed."""
    obb = _openbb_app()
    last_error: Exception | None = None
    frame = pd.DataFrame()

    for attempt in range(3):
        try:
            frame = obb.equity.price.quote(symbol, provider="yfinance").to_df()
            if not frame.empty:
                break
        except Exception as exc:  # OpenBB providers can return transient empty objects.
            last_error = exc
        if attempt < 2:
            sleep(1.5 * (attempt + 1))

    if frame.empty:
        raise ValueError(f"no quote returned for {symbol}") from last_error

    row: dict[str, Any] = frame.iloc[0].to_dict()
    last_price = first_positive(
        row.get("last_price"),
        row.get("price"),
        row.get("regular_market_price"),
        row.get("ask"),
        row.get("bid"),
        row.get("prev_close"),
        row.get("previous_close"),
    )
    previous_close = row.get("prev_close") or row.get("previous_close")

    return QuoteSnapshot(
        symbol=str(row.get("symbol", symbol)),
        name=row.get("name"),
        exchange=row.get("exchange"),
        last_price=scalar_float_or_none(last_price),
        previous_close=scalar_float_or_none(previous_close),
        currency=row.get("currency"),
        provider="openbb:yfinance",
    )


def fetch_yfinance_quote(symbol: str) -> QuoteSnapshot:
    """Fetch a current quote directly through yfinance."""
    ticker = yf.Ticker(symbol)
    info: dict[str, Any] = {}
    fast_info: dict[str, Any] = {}

    try:
        raw_fast_info = ticker.fast_info
        fast_info = dict(raw_fast_info.items()) if hasattr(raw_fast_info, "items") else {}
    except Exception:
        fast_info = {}

    try:
        raw_info = ticker.info
        info = raw_info if isinstance(raw_info, dict) else {}
    except Exception:
        info = {}

    last_price = first_positive(
        fast_info.get("last_price"),
        fast_info.get("lastPrice"),
        info.get("currentPrice"),
        info.get("regularMarketPrice"),
        info.get("ask"),
        info.get("bid"),
        info.get("previousClose"),
    )
    previous_close = fast_info.get("previous_close") or info.get("previousClose")

    if last_price is None and previous_close is None:
        raise ValueError(f"no quote returned for {symbol}")

    return QuoteSnapshot(
        symbol=str(info.get("symbol") or symbol).upper(),
        name=info.get("shortName") or info.get("longName"),
        exchange=info.get("exchange") or fast_info.get("exchange"),
        last_price=scalar_float_or_none(last_price),
        previous_close=scalar_float_or_none(previous_close),
        currency=info.get("currency") or fast_info.get("currency"),
        provider="yfinance",
    )


def fetch_quote_snapshot(symbol: str) -> QuoteSnapshot:
    """Fetch a quote through OpenBB when available, otherwise yfinance."""
    try:
        return fetch_openbb_quote(symbol)
    except OptionalProviderUnavailable:
        return fetch_yfinance_quote(symbol)


def first_positive(*values: Any) -> float | None:
    for value in values:
        if pd.notna(value):
            number = float(value)
            if number > 0:
                return number
    return None


def scalar_float_or_none(value: Any) -> float | None:
    if value is None or not pd.notna(value):
        return None
    return float(value)


AdjustmentMode = Literal["raw", "auto_adjust"]


def fetch_yfinance_history(
    symbol: str,
    start: str,
    end: str,
    *,
    adjustment: AdjustmentMode = "auto_adjust",
) -> pd.DataFrame:
    """Fetch OHLCV history with yfinance and normalize it for local tools."""
    raw = yf.download(
        symbol,
        start=start,
        end=end,
        auto_adjust=adjustment == "auto_adjust",
        progress=False,
        threads=False,
    )
    if raw.empty:
        raise ValueError(f"no historical prices returned for {symbol}")

    frame = raw.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)

    frame = frame.reset_index()
    frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    if "date" not in frame.columns:
        first = frame.columns[0]
        frame = frame.rename(columns={first: "date"})

    columns = ["date", "open", "high", "low", "close", "volume"]
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"historical data missing columns: {missing}")

    normalized = frame[columns].copy()
    normalized["date"] = pd.to_datetime(normalized["date"]).dt.date
    return normalized


def write_history_csv(history: pd.DataFrame, path: Path) -> None:
    """Persist normalized OHLCV data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(path, index=False)
