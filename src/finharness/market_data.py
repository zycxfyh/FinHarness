"""Thin market-data governance around mature finance wheels.

FinHarness owns the evidence boundary. OpenBB/yfinance/NautilusTrader own the
heavy data access, trading-domain models, and catalog storage semantics.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import pandas as pd
import yfinance as yf
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "data" / "raw" / "market-data"
NORMALIZED_ROOT = ROOT / "data" / "normalized" / "market-data"
RECEIPT_ROOT = ROOT / "data" / "receipts" / "market-data"
NAUTILUS_CATALOG_ROOT = ROOT / "data" / "catalog" / "nautilus"


class SourceSpec(BaseModel):
    """Source layer: which mature provider owns the upstream data call."""

    model_config = ConfigDict(frozen=True)

    provider: str
    upstream_source: str
    asset_class: str
    dataset: str
    access_method: Literal["api_pull", "websocket", "batch", "broker_export"]
    wheel: str
    wheel_version: str | None = None


class MarketDataQuality(BaseModel):
    """Quality layer: explicit checks and flags around wheel output."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    row_count: int
    missing_required_columns: list[str] = Field(default_factory=list)
    duplicate_timestamps: int = 0
    null_counts: dict[str, int] = Field(default_factory=dict)
    stale: bool = False
    outlier_flags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MarketDataLineage(BaseModel):
    """Lineage layer: machine-readable evidence for the data transformation."""

    model_config = ConfigDict(frozen=True)

    source: SourceSpec
    fetched_at_utc: str
    fetch_config: dict[str, Any]
    raw_hash: str
    normalized_hash: str
    transform_version: str = "finharness.market_data.v1"
    raw_ref: str
    normalized_ref: str
    catalog_ref: str | None = None


class MarketDataSnapshot(BaseModel):
    """Snapshot layer: stable object consumed by research, risk, and execution."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    as_of_utc: str
    symbols: list[str]
    fields: list[str]
    timeframe: str
    adjusted: bool
    quality: MarketDataQuality
    lineage: MarketDataLineage
    payload_ref: str
    receipt_ref: str


class DataReceipt(BaseModel):
    """Receipt layer: durable evidence root for a data workflow."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "market_data_ingestion"
    eight_layer_map: dict[str, str]
    snapshot: MarketDataSnapshot


@dataclass(frozen=True)
class MarketDataBundle:
    snapshot: MarketDataSnapshot
    close: pd.DataFrame
    history: pd.DataFrame | None = None
    receipt: DataReceipt | None = None


def package_version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    )


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def normalize_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize wheel output into the local OHLCV contract."""
    normalized = frame.copy()
    if isinstance(normalized.columns, pd.MultiIndex):
        normalized.columns = normalized.columns.get_level_values(0)
    normalized = normalized.reset_index()
    normalized.columns = [
        str(column).strip().lower().replace(" ", "_") for column in normalized.columns
    ]
    if "date" not in normalized.columns:
        normalized = normalized.rename(columns={normalized.columns[0]: "date"})

    required = ["date", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in normalized.columns]
    if missing:
        raise ValueError(f"historical data missing columns: {missing}")

    output = normalized[required].copy()
    output["date"] = pd.to_datetime(output["date"], utc=True)
    return output


def build_quality_report(
    frame: pd.DataFrame,
    *,
    required_columns: list[str],
    max_staleness_days: int | None = None,
) -> MarketDataQuality:
    missing = [column for column in required_columns if column not in frame.columns]
    duplicate_timestamps = 0
    stale = False
    notes: list[str] = []
    outlier_flags: list[str] = []

    if "date" in frame.columns:
        duplicate_timestamps = int(frame["date"].duplicated().sum())
        latest = pd.to_datetime(frame["date"], utc=True).max()
        if pd.notna(latest) and max_staleness_days is not None:
            age_days = (datetime.now(UTC) - latest.to_pydatetime()).days
            stale = age_days > max_staleness_days
            if stale:
                notes.append(f"latest bar is {age_days} days old")

    for column in ["open", "high", "low", "close"]:
        if column in frame.columns and (frame[column].astype(float) <= 0).any():
            outlier_flags.append(f"{column}_non_positive")

    if {"high", "low"}.issubset(frame.columns):
        invalid = frame["high"].astype(float) < frame["low"].astype(float)
        if invalid.any():
            outlier_flags.append("high_below_low")

    null_counts = {
        column: int(frame[column].isna().sum())
        for column in frame.columns
        if int(frame[column].isna().sum()) > 0
    }
    ok = not missing and duplicate_timestamps == 0 and not outlier_flags
    return MarketDataQuality(
        ok=ok,
        row_count=len(frame),
        missing_required_columns=missing,
        duplicate_timestamps=duplicate_timestamps,
        null_counts=null_counts,
        stale=stale,
        outlier_flags=outlier_flags,
        notes=notes,
    )


def nautilus_bar_type(symbol: str, venue: str = "YFINANCE", timeframe: str = "1-DAY") -> BarType:
    return BarType.from_str(f"{symbol}.{venue}-{timeframe}-LAST-EXTERNAL")


def ohlcv_to_nautilus_bars(
    history: pd.DataFrame,
    *,
    symbol: str,
    venue: str = "YFINANCE",
    timeframe: str = "1-DAY",
) -> list[Bar]:
    """Convert normalized OHLCV into NautilusTrader Bar objects."""
    bar_type = nautilus_bar_type(symbol, venue=venue, timeframe=timeframe)
    bars: list[Bar] = []
    for row in history.itertuples(index=False):
        ts_event = int(pd.Timestamp(row.date).timestamp() * 1_000_000_000)
        bars.append(
            Bar(
                bar_type,
                Price.from_str(f"{float(row.open):.8f}"),
                Price.from_str(f"{float(row.high):.8f}"),
                Price.from_str(f"{float(row.low):.8f}"),
                Price.from_str(f"{float(row.close):.8f}"),
                Quantity.from_int(max(int(float(row.volume)), 0)),
                ts_event,
                ts_event,
            )
        )
    return bars


def write_nautilus_catalog(
    bars: list[Bar],
    *,
    catalog_root: Path = NAUTILUS_CATALOG_ROOT,
) -> str | None:
    if not bars:
        return None
    catalog_root.mkdir(parents=True, exist_ok=True)
    catalog = ParquetDataCatalog(str(catalog_root))
    catalog.write_data(bars)
    return display_path(catalog_root)


def persist_market_data_snapshot(
    *,
    source: SourceSpec,
    fetch_config: dict[str, Any],
    raw_payload: dict[str, Any],
    normalized_payload: dict[str, Any],
    quality: MarketDataQuality,
    symbols: list[str],
    fields: list[str],
    timeframe: str,
    adjusted: bool,
    as_of_utc: str,
    catalog_ref: str | None = None,
) -> DataReceipt:
    snapshot_id = f"mds_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    receipt_id = f"receipt_{snapshot_id}"

    raw_text = json.dumps(raw_payload, ensure_ascii=False, sort_keys=True, default=str)
    normalized_text = json.dumps(
        normalized_payload,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    raw_ref = RAW_ROOT / f"{snapshot_id}.json"
    normalized_ref = NORMALIZED_ROOT / f"{snapshot_id}.json"
    receipt_ref = RECEIPT_ROOT / f"{receipt_id}.json"

    lineage = MarketDataLineage(
        source=source,
        fetched_at_utc=now_utc(),
        fetch_config=fetch_config,
        raw_hash=sha256_text(raw_text),
        normalized_hash=sha256_text(normalized_text),
        raw_ref=display_path(raw_ref),
        normalized_ref=display_path(normalized_ref),
        catalog_ref=catalog_ref,
    )
    snapshot = MarketDataSnapshot(
        snapshot_id=snapshot_id,
        as_of_utc=as_of_utc,
        symbols=symbols,
        fields=fields,
        timeframe=timeframe,
        adjusted=adjusted,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(normalized_ref),
        receipt_ref=display_path(receipt_ref),
    )
    receipt = DataReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        eight_layer_map={
            "source": source.provider,
            "ingestion": source.access_method,
            "normalization": "FinHarness OHLCV contract + Nautilus Bar adapter",
            "quality": "MarketDataQuality",
            "storage": "raw JSON + normalized JSON + optional Nautilus ParquetDataCatalog",
            "snapshot": "MarketDataSnapshot",
            "lineage": "MarketDataLineage",
            "consumer": "research/backtest/risk/execution/reporting",
        },
        snapshot=snapshot,
    )

    write_json(raw_ref, raw_payload)
    write_json(normalized_ref, normalized_payload)
    write_json(receipt_ref, receipt.model_dump(mode="json"))
    return receipt


def build_ohlcv_snapshot_from_history(
    history: pd.DataFrame,
    *,
    symbol: str,
    source: SourceSpec,
    fetch_config: dict[str, Any],
    raw_payload: dict[str, Any],
    adjusted: bool,
    write_catalog: bool = True,
) -> DataReceipt:
    required = ["date", "open", "high", "low", "close", "volume"]
    quality = build_quality_report(
        history,
        required_columns=required,
        max_staleness_days=None,
    )
    bars = ohlcv_to_nautilus_bars(history, symbol=symbol) if write_catalog else []
    catalog_ref = write_nautilus_catalog(bars) if bars else None
    as_of = pd.to_datetime(history["date"], utc=True).max().isoformat()
    normalized_payload = {
        "records": history.to_dict(orient="records"),
        "nautilus_bar_type": str(nautilus_bar_type(symbol)),
        "nautilus_bar_count": len(bars),
    }
    return persist_market_data_snapshot(
        source=source,
        fetch_config=fetch_config,
        raw_payload=raw_payload,
        normalized_payload=normalized_payload,
        quality=quality,
        symbols=[symbol],
        fields=required,
        timeframe="1-DAY",
        adjusted=adjusted,
        as_of_utc=as_of,
        catalog_ref=catalog_ref,
    )


def fetch_yfinance_close_snapshot(
    universe: list[str],
    *,
    period: str = "6mo",
    adjusted: bool = False,
) -> MarketDataBundle:
    """Fetch a close matrix through yfinance and wrap it in a receipt."""
    raw = yf.download(
        universe,
        period=period,
        auto_adjust=adjusted,
        progress=False,
        threads=False,
    )
    if raw.empty:
        raise ValueError(f"no yfinance data returned for {universe}")

    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=universe[0])
    close = close.dropna(axis=1, how="all").dropna()
    if close.empty:
        raise ValueError("close price matrix is empty after normalization")

    close = close.copy()
    close.index = pd.to_datetime(close.index, utc=True)
    frame = close.reset_index().rename(columns={close.index.name or "index": "date"})
    quality = build_quality_report(
        frame,
        required_columns=["date", *list(close.columns)],
        max_staleness_days=None,
    )
    source = SourceSpec(
        provider="yfinance",
        upstream_source="Yahoo Finance",
        asset_class="equity",
        dataset="close_matrix",
        access_method="api_pull",
        wheel="yfinance",
        wheel_version=package_version("yfinance"),
    )
    receipt = persist_market_data_snapshot(
        source=source,
        fetch_config={"universe": universe, "period": period, "auto_adjust": adjusted},
        raw_payload={"columns": [str(column) for column in raw.columns], "rows": len(raw)},
        normalized_payload={"records": frame.to_dict(orient="records")},
        quality=quality,
        symbols=list(close.columns),
        fields=["date", *list(close.columns)],
        timeframe=f"period:{period}",
        adjusted=adjusted,
        as_of_utc=close.index.max().isoformat(),
    )
    return MarketDataBundle(snapshot=receipt.snapshot, close=close, receipt=receipt)
