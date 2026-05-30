"""Data entry layer built on top community wheels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import sleep
from typing import Any

import pandas as pd
import yfinance as yf
from openbb import obb


@dataclass(frozen=True)
class QuoteSnapshot:
    symbol: str
    name: str | None
    exchange: str | None
    last_price: float | None
    previous_close: float | None
    currency: str | None
    provider: str


def fetch_openbb_quote(symbol: str) -> QuoteSnapshot:
    """Fetch a current quote through OpenBB's yfinance provider."""
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
        last_price=float(last_price) if pd.notna(last_price) else None,
        previous_close=float(previous_close) if pd.notna(previous_close) else None,
        currency=row.get("currency"),
        provider="openbb:yfinance",
    )


def first_positive(*values: Any) -> float | None:
    for value in values:
        if pd.notna(value):
            number = float(value)
            if number > 0:
                return number
    return None


def fetch_yfinance_history(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch OHLCV history with yfinance and normalize it for local tools."""
    raw = yf.download(
        symbol,
        start=start,
        end=end,
        auto_adjust=False,
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
