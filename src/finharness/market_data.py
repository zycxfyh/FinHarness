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

from finharness.data_quality import (
    DATA_QUALITY_BACKEND,
    data_quality_backend_version,
    price_outlier_flags,
)

ROOT = Path(__file__).resolve().parents[2]
RAW_ROOT = ROOT / "data" / "raw" / "market-data"
NORMALIZED_ROOT = ROOT / "data" / "normalized" / "market-data"
RECEIPT_ROOT = ROOT / "data" / "receipts" / "market-data"
NAUTILUS_CATALOG_ROOT = ROOT / "data" / "catalog" / "nautilus"
AdjustmentMode = Literal["raw", "auto_adjust"]
DEFAULT_DATA_BIAS_CONTROLS = [
    "survivorship_uncontrolled",
    "point_in_time_uncontrolled",
]


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
    adjustment: AdjustmentMode = "auto_adjust"


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
    reconciliation: dict[str, Any] | None = None


class MarketDataLineage(BaseModel):
    """Lineage layer: machine-readable evidence for the data transformation."""

    model_config = ConfigDict(frozen=True)

    source: SourceSpec
    fetched_at_utc: str
    fetch_config: dict[str, Any]
    raw_hash: str
    normalized_hash: str
    transform_version: str = "finharness.market_data.v1"
    quality_backend: str | None = None
    quality_backend_version: str | None = None
    raw_ref: str
    normalized_ref: str
    catalog_ref: str | None = None
    data_bias_controls: list[str] = Field(default_factory=lambda: list(DEFAULT_DATA_BIAS_CONTROLS))


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


def adjustment_from_adjusted(adjusted: bool) -> AdjustmentMode:
    return "auto_adjust" if adjusted else "raw"


def adjusted_from_adjustment(adjustment: AdjustmentMode) -> bool:
    return adjustment == "auto_adjust"


def default_reconciliation(reason: str = "no second provider configured") -> dict[str, Any]:
    return {
        "status": "single_source_unreconciled",
        "reason": reason,
    }


def reconcile_close(
    symbol: str,
    start: str,
    end: str,
    *,
    primary_history: pd.DataFrame | None = None,
    second_provider: Any | None = None,
    adjustment: AdjustmentMode = "auto_adjust",
) -> dict[str, Any]:
    """Best-effort close-price reconciliation against a second source.

    Reconciliation is evidence-quality disclosure only. Missing providers,
    credentials, empty overlap, or provider errors fail open to a
    ``single_source_unreconciled`` status.
    """
    if second_provider is None:
        return default_reconciliation()
    if primary_history is None or primary_history.empty:
        return default_reconciliation("primary history unavailable")

    try:
        if callable(second_provider):
            secondary = second_provider(
                symbol,
                start,
                end,
                adjustment=adjustment,
            )
            second_provider_name = getattr(second_provider, "__name__", "callable")
        else:
            secondary = _fetch_openbb_history(
                symbol,
                start,
                end,
                provider=str(second_provider),
            )
            second_provider_name = f"openbb:{second_provider}"
    except Exception as exc:
        return default_reconciliation(f"second provider unavailable: {exc}")

    try:
        primary_close = _close_by_date(primary_history)
        secondary_close = _close_by_date(secondary)
        joined = pd.concat(
            [primary_close.rename("primary"), secondary_close.rename("secondary")],
            axis=1,
            join="inner",
        ).dropna()
    except Exception as exc:
        return default_reconciliation(f"reconciliation normalization failed: {exc}")

    if joined.empty:
        return default_reconciliation("no overlapping close prices")

    denominator = joined["primary"].abs().replace(0.0, pd.NA)
    divergence = ((joined["primary"] - joined["secondary"]).abs() / denominator) * 100.0
    divergence = divergence.dropna()
    if divergence.empty:
        return default_reconciliation("no positive primary close prices in overlap")
    return {
        "status": "reconciled",
        "provider": "yfinance",
        "second_provider": second_provider_name,
        "max_close_divergence_pct": float(divergence.max()),
        "overlap_rows": int(len(joined)),
        "adjustment": adjustment,
    }


def data_bias_limitation(
    *,
    adjustment: str = "auto_adjust",
    reconciliation: dict[str, Any] | None = None,
    data_bias_controls: list[str] | None = None,
) -> str:
    controls = data_bias_controls or DEFAULT_DATA_BIAS_CONTROLS
    reconciliation_status = (reconciliation or default_reconciliation()).get(
        "status",
        "single_source_unreconciled",
    )
    controls_text = ", ".join(controls)
    return (
        "Data bias uncontrolled: survivorship and point-in-time are not assured; "
        f"prices {adjustment}; reconciliation {reconciliation_status}; "
        f"controls {controls_text}. Evidence only."
    )


def _close_by_date(frame: pd.DataFrame) -> pd.Series:
    if "date" not in frame.columns or "close" not in frame.columns:
        normalized = normalize_ohlcv(frame)
    else:
        normalized = frame[["date", "close"]].copy()
    dates = pd.to_datetime(normalized["date"], utc=True).dt.normalize()
    close = normalized["close"].astype(float)
    return pd.Series(close.to_numpy(), index=dates).sort_index()


def _fetch_openbb_history(symbol: str, start: str, end: str, *, provider: str) -> pd.DataFrame:
    from openbb import obb

    frame = obb.equity.price.historical(
        symbol,
        start_date=start,
        end_date=end,
        provider=provider,
    ).to_df()
    if frame.empty:
        raise ValueError(f"no OpenBB history returned for {symbol} via {provider}")
    return normalize_ohlcv(frame)


def build_quality_report(
    frame: pd.DataFrame,
    *,
    required_columns: list[str],
    max_staleness_days: int | None = None,
    reconciliation: dict[str, Any] | None = None,
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

    present_ohlc = [
        column for column in ("open", "high", "low", "close") if column in frame.columns
    ]
    if present_ohlc:
        numeric_ohlc = frame[present_ohlc].astype(float)
        outlier_flags = price_outlier_flags(numeric_ohlc)

    null_counts = {
        column: int(frame[column].isna().sum())
        for column in frame.columns
        if int(frame[column].isna().sum()) > 0
    }
    ok = not missing and duplicate_timestamps == 0 and not outlier_flags
    quality_notes = notes
    if reconciliation and reconciliation.get("status") == "single_source_unreconciled":
        quality_notes = [
            *quality_notes,
            f"close reconciliation: {reconciliation['status']}",
        ]
    return MarketDataQuality(
        ok=ok,
        row_count=len(frame),
        missing_required_columns=missing,
        duplicate_timestamps=duplicate_timestamps,
        null_counts=null_counts,
        stale=stale,
        outlier_flags=outlier_flags,
        notes=quality_notes,
        reconciliation=reconciliation,
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
    data_bias_controls: list[str] | None = None,
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

    adjustment = source.adjustment or adjustment_from_adjusted(adjusted)
    lineage_fetch_config = {
        **fetch_config,
        "adjustment": fetch_config.get("adjustment", adjustment),
        "auto_adjust": fetch_config.get("auto_adjust", adjusted),
    }
    lineage = MarketDataLineage(
        source=source,
        fetched_at_utc=now_utc(),
        fetch_config=lineage_fetch_config,
        raw_hash=sha256_text(raw_text),
        normalized_hash=sha256_text(normalized_text),
        quality_backend=DATA_QUALITY_BACKEND,
        quality_backend_version=data_quality_backend_version(),
        raw_ref=display_path(raw_ref),
        normalized_ref=display_path(normalized_ref),
        catalog_ref=catalog_ref,
        data_bias_controls=data_bias_controls or list(DEFAULT_DATA_BIAS_CONTROLS),
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
    adjustment: AdjustmentMode | None = None,
    quality: MarketDataQuality | None = None,
    reconciliation: dict[str, Any] | None = None,
    data_bias_controls: list[str] | None = None,
) -> DataReceipt:
    required = ["date", "open", "high", "low", "close", "volume"]
    adjustment_mode = adjustment or adjustment_from_adjusted(adjusted)
    if source.adjustment != adjustment_mode:
        source = source.model_copy(update={"adjustment": adjustment_mode})
    if quality is None:
        quality = build_quality_report(
            history,
            required_columns=required,
            max_staleness_days=None,
            reconciliation=reconciliation,
        )
    bars = ohlcv_to_nautilus_bars(history, symbol=symbol) if write_catalog else []
    catalog_ref = None
    catalog_notes: list[str] = []
    if bars:
        try:
            catalog_ref = write_nautilus_catalog(bars)
        except ValueError as exc:
            # Nautilus ParquetDataCatalog rejects overlapping intervals. That
            # should not make the research evidence unavailable: keep the
            # market-data receipt, but expose the catalog degradation so the
            # cockpit can show it instead of silently hiding the problem.
            catalog_notes.append(f"nautilus catalog write skipped: {exc}")
    if catalog_notes:
        quality = quality.model_copy(update={"notes": [*quality.notes, *catalog_notes]})
    as_of = pd.to_datetime(history["date"], utc=True).max().isoformat()
    normalized_payload = {
        "records": history.to_dict(orient="records"),
        "nautilus_bar_type": str(nautilus_bar_type(symbol)),
        "nautilus_bar_count": len(bars),
    }
    return persist_market_data_snapshot(
        source=source,
        fetch_config={
            **fetch_config,
            "adjustment": fetch_config.get("adjustment", adjustment_mode),
            "auto_adjust": fetch_config.get("auto_adjust", adjusted),
        },
        raw_payload=raw_payload,
        normalized_payload=normalized_payload,
        quality=quality,
        symbols=[symbol],
        fields=required,
        timeframe="1-DAY",
        adjusted=adjusted,
        as_of_utc=as_of,
        catalog_ref=catalog_ref,
        data_bias_controls=data_bias_controls,
    )


def fetch_yfinance_close_snapshot(
    universe: list[str],
    *,
    period: str = "6mo",
    adjusted: bool = True,
) -> MarketDataBundle:
    """Fetch a close matrix through yfinance and wrap it in a receipt."""
    adjustment = adjustment_from_adjusted(adjusted)
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
        reconciliation=default_reconciliation(),
    )
    source = SourceSpec(
        provider="yfinance",
        upstream_source="Yahoo Finance",
        asset_class="equity",
        dataset="close_matrix",
        access_method="api_pull",
        wheel="yfinance",
        wheel_version=package_version("yfinance"),
        adjustment=adjustment,
    )
    receipt = persist_market_data_snapshot(
        source=source,
        fetch_config={
            "universe": universe,
            "period": period,
            "auto_adjust": adjusted,
            "adjustment": adjustment,
        },
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
