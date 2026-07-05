"""Data catalog v0 — read-only visibility surface over market-data receipts.

Reads existing DataReceipt JSON files from the market-data receipt root.
No network calls. No ingestion. No Agent/scenario/paper integration.

Malformed or missing receipts become data gaps, not unhandled exceptions.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.data_quality_policy import (
    DataQualityFinding,
    build_quality_report,
)
from finharness.market_data import (
    RECEIPT_ROOT,
    DataReceipt,
    MarketDataQuality,
    MarketDataSnapshot,
    SourceSpec,
)

DATA_CATALOG_NON_CLAIMS = (
    "Read-only data catalog surface.",
    "No network calls triggered.",
    "No execution authorization.",
    "No provider fetch or refresh.",
    "Single-source data may have survivorship / point-in-time bias.",
)


class DataSourceRegistryEntry(BaseModel):
    """Registry entry describing a known market-data provider."""

    model_config = ConfigDict(frozen=True)

    data_source_id: str
    provider: str
    display_name: str
    upstream_source: str
    asset_classes: list[str]
    datasets: list[str]
    access_method: Literal["api_pull", "websocket", "batch", "broker_export"]
    wheel: str
    credential_required: bool = False
    network_required: bool = True
    default_adjustment: str = "auto_adjust"
    freshness_policy: str = "per_ingestion"
    bias_controls: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    execution_allowed: bool = False


class DataCatalogEntry(BaseModel):
    """Catalog entry built from a discovered local market-data receipt."""

    model_config = ConfigDict(from_attributes=True)

    dataset_key: str
    data_source_id: str
    provider: str
    asset_class: str
    dataset: str
    symbols: list[str]
    fields: list[str]
    timeframe: str
    latest_snapshot_id: str
    latest_as_of_utc: str
    latest_receipt_ref: str
    quality_summary: dict[str, object] = Field(default_factory=dict)
    reconciliation_status: str = "single_source_unreconciled"
    bias_controls: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    freshness_status: str = "unknown"
    quality_status: str = "unknown"
    bias_status: str = "uncontrolled"
    readiness_status: str = "not_ready"
    findings: list[DataQualityFinding] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    execution_allowed: bool = False


class DataGap(BaseModel):
    """Surfaced data gap that blocks downstream confidence."""

    model_config = ConfigDict(frozen=True)

    gap_id: str
    severity: Literal["info", "warning", "critical"]
    scope: str
    message: str
    source_ref: str | None = None
    blocks: list[str] = Field(default_factory=list)


class DataCatalogView(BaseModel):
    """Aggregated catalog view returned by listing endpoints."""

    model_config = ConfigDict(frozen=True)

    sources: list[DataSourceRegistryEntry]
    catalog_entries: list[DataCatalogEntry]
    data_gaps: list[DataGap]
    source_refs: tuple[str, ...]
    non_claims: tuple[str, ...] = DATA_CATALOG_NON_CLAIMS
    execution_allowed: bool = False


def _quality_summary(quality: MarketDataQuality) -> dict[str, object]:
    return {
        "ok": quality.ok,
        "row_count": quality.row_count,
        "missing_required_columns": quality.missing_required_columns,
        "duplicate_timestamps": quality.duplicate_timestamps,
        "stale": quality.stale,
        "outlier_flags": quality.outlier_flags,
        "null_counts": quality.null_counts,
    }


def _dataset_key(source: SourceSpec, snapshot: MarketDataSnapshot) -> str:
    return f"{source.provider}/{source.dataset}/{':'.join(sorted(snapshot.symbols))}"


def default_data_source_registry() -> list[DataSourceRegistryEntry]:
    """Return the built-in registry of known data sources.

    Includes yfinance as the primary market-data provider.
    OpenBB reconciliation is noted as a limitation, not an active default dependency.
    """
    return [
        DataSourceRegistryEntry(
            data_source_id="yfinance_equity",
            provider="yfinance",
            display_name="Yahoo Finance (via yfinance)",
            upstream_source="Yahoo Finance",
            asset_classes=["equity"],
            datasets=["ohlcv_history", "close_matrix"],
            access_method="api_pull",
            wheel="yfinance",
            credential_required=False,
            network_required=True,
            default_adjustment="auto_adjust",
            freshness_policy="per_ingestion",
            bias_controls=[
                "survivorship_uncontrolled",
                "point_in_time_uncontrolled",
            ],
            limitations=[
                "Single provider — close prices are unreconciled by default.",
                "OpenBB reconciliation not configured as an active default.",
                "Survivorship and point-in-time bias not controlled.",
                "No real-time streaming.",
            ],
        ),
    ]


def discover_market_data_receipts(
    receipt_root: Path | None = None,
) -> list[DataReceipt]:
    """Discover market-data receipts from the local filesystem.

    No network calls. Missing directory returns empty list.
    Malformed JSON becomes a data gap, not an exception — callers should
    inspect returned data_gaps alongside receipts.
    """
    root = receipt_root or RECEIPT_ROOT
    if not root.is_dir():
        return []

    receipts: list[DataReceipt] = []
    for path in sorted(root.glob("receipt_mds_*.json")):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            receipts.append(DataReceipt.model_validate(payload))
        except (json.JSONDecodeError, ValueError):
            # Malformed receipt — skip here; build_data_catalog surfaces the gap.
            continue
    return receipts


def _receipt_to_catalog_entry(receipt: DataReceipt) -> DataCatalogEntry:
    """Convert a single DataReceipt into a DataCatalogEntry."""
    snapshot = receipt.snapshot
    lineage = snapshot.lineage
    source = lineage.source
    key = _dataset_key(source, snapshot)

    quality = snapshot.quality
    reconciliation_status = (
        quality.reconciliation.get("status", "single_source_unreconciled")
        if quality.reconciliation
        else "single_source_unreconciled"
    )

    entry_gaps: list[str] = []
    if not quality.ok:
        entry_gaps.append(f"quality check failed: {quality.notes}")
    if quality.stale:
        entry_gaps.append("data is stale")
    if reconciliation_status == "single_source_unreconciled":
        entry_gaps.append("close prices unreconciled — single source only")

    try:
        bias_controls = list(lineage.data_bias_controls or [])
    except (AttributeError, TypeError):
        bias_controls = []

    qr = build_quality_report(
        dataset_key=key,
        as_of_utc=snapshot.as_of_utc,
        latest_receipt_ref=snapshot.receipt_ref,
        quality=quality,
        reconciliation_status=reconciliation_status,
        bias_controls=bias_controls,
    )

    return DataCatalogEntry(
        dataset_key=key,
        data_source_id=f"{source.provider}_{source.asset_class}",
        provider=source.provider,
        asset_class=source.asset_class,
        dataset=source.dataset,
        symbols=list(snapshot.symbols),
        fields=list(snapshot.fields),
        timeframe=snapshot.timeframe,
        latest_snapshot_id=snapshot.snapshot_id,
        latest_as_of_utc=snapshot.as_of_utc,
        latest_receipt_ref=snapshot.receipt_ref,
        quality_summary=_quality_summary(quality),
        reconciliation_status=reconciliation_status,
        bias_controls=bias_controls,
        data_gaps=entry_gaps,
        freshness_status=qr.freshness_status,
        quality_status=qr.quality_status,
        bias_status=qr.bias_status,
        readiness_status=qr.readiness_status,
        findings=qr.findings,
        blocks=qr.blocks,
    )


def _surface_malformed_as_gaps(
    root: Path,
    gap_idx: int,
) -> tuple[list[DataGap], int]:
    """Surface receipts that failed to parse as data gaps."""
    gaps: list[DataGap] = []
    for path in sorted(root.glob("receipt_mds_*.json")):
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            DataReceipt.model_validate(payload)
        except (json.JSONDecodeError, ValueError):
            gap_idx += 1
            gaps.append(
                DataGap(
                    gap_id=f"dg_{gap_idx:04d}",
                    severity="critical",
                    scope="receipt_parse",
                    message="Malformed receipt JSON — cannot load.",
                    source_ref=str(path),
                    blocks=["catalog_population", "quality_inspection"],
                )
            )
    return gaps, gap_idx


def _surface_registry_coverage_gaps(
    registry: list[DataSourceRegistryEntry],
    discovered_dataset_keys: set[str],
    gap_idx: int,
) -> tuple[list[DataGap], int]:
    """Surface gaps for registry sources not backed by any receipt."""
    gaps: list[DataGap] = []
    registry_dataset_keys: set[str] = set()
    for src in registry:
        for ds in src.datasets:
            registry_dataset_keys.add(f"{src.provider}/{ds}")
    discovered_prefixes = {k.rsplit("/", 1)[0] for k in discovered_dataset_keys}
    for missing_key in sorted(registry_dataset_keys - discovered_prefixes):
        gap_idx += 1
        gaps.append(
            DataGap(
                gap_id=f"dg_{gap_idx:04d}",
                severity="warning",
                scope="registry_coverage",
                message=f"No receipt found in the registered dataset {missing_key}.",
                blocks=["coverage_verification"],
            )
        )
    return gaps, gap_idx


def build_data_catalog(
    receipt_root: Path | None = None,
) -> DataCatalogView:
    """Build the read-only data catalog from local receipts and the default registry.

    Reads receipts from disk only — no network calls.
    Missing or malformed receipts produce data gaps, not exceptions.
    """
    registry = default_data_source_registry()
    receipts = discover_market_data_receipts(receipt_root)
    root = receipt_root or RECEIPT_ROOT

    gaps: list[DataGap] = []
    gap_idx = 0

    if not root.is_dir():
        gap_idx += 1
        gaps.append(
            DataGap(
                gap_id=f"dg_{gap_idx:04d}",
                severity="critical",
                scope="receipt_root",
                message="Market-data receipt directory does not exist.",
                source_ref=str(root),
                blocks=["catalog_discovery", "quality_inspection"],
            )
        )
        return DataCatalogView(
            sources=registry,
            catalog_entries=[],
            data_gaps=gaps,
            source_refs=(),
        )

    if not receipts:
        gap_idx += 1
        gaps.append(
            DataGap(
                gap_id=f"dg_{gap_idx:04d}",
                severity="warning",
                scope="receipt_discovery",
                message="No market-data receipts found in receipt root.",
                source_ref=str(root),
                blocks=["catalog_population", "quality_inspection"],
            )
        )

    # Build catalog entries from receipts.
    entries: dict[str, DataCatalogEntry] = {}
    for receipt in receipts:
        entry = _receipt_to_catalog_entry(receipt)
        key = entry.dataset_key
        existing = entries.get(key)
        if existing is None or entry.latest_as_of_utc > existing.latest_as_of_utc:
            entries[key] = entry

    # Surface malformed receipts and registry coverage as gaps.
    malformed_gaps, gap_idx = _surface_malformed_as_gaps(root, gap_idx)
    gaps.extend(malformed_gaps)
    registry_gaps, gap_idx = _surface_registry_coverage_gaps(
        registry, set(entries.keys()), gap_idx
    )
    gaps.extend(registry_gaps)

    all_source_refs = tuple(
        sorted({entry.latest_receipt_ref for entry in entries.values()})
    )

    return DataCatalogView(
        sources=registry,
        catalog_entries=sorted(entries.values(), key=lambda e: e.dataset_key),
        data_gaps=gaps,
        source_refs=all_source_refs,
    )


def get_catalog_entry(
    dataset_key: str,
    receipt_root: Path | None = None,
) -> DataCatalogEntry | None:
    """Look up a single catalog entry by dataset key.

    Returns None if no entry matches.
    """
    view = build_data_catalog(receipt_root)
    for entry in view.catalog_entries:
        if entry.dataset_key == dataset_key:
            return entry
    return None
