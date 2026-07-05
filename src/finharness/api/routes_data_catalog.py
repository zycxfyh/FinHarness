"""Read-only data catalog API routes.

Exposes data source registry, catalog entries, and data gaps.
All endpoints are GET-only. No network calls. No write operations.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from finharness.api.dependencies import MarketDataReceiptRootDependency
from finharness.data_catalog import (
    DataCatalogEntry,
    DataGap,
    DataSourceRegistryEntry,
    build_data_catalog,
    get_catalog_entry,
)

router = APIRouter(tags=["data"])

DATA_CATALOG_NON_CLAIMS = (
    "Read-only data catalog surface.",
    "No network calls triggered.",
    "No execution authorization.",
    "No provider fetch or refresh.",
)


class SourcesResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sources: list[DataSourceRegistryEntry]
    non_claims: tuple[str, ...] = DATA_CATALOG_NON_CLAIMS
    execution_allowed: bool = False


class CatalogListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    catalog_entries: list[DataCatalogEntry]
    data_gaps: list[DataGap]
    source_refs: tuple[str, ...]
    non_claims: tuple[str, ...] = DATA_CATALOG_NON_CLAIMS
    execution_allowed: bool = False


class CatalogDetailResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    entry: DataCatalogEntry | None
    non_claims: tuple[str, ...] = DATA_CATALOG_NON_CLAIMS
    execution_allowed: bool = False


class GapsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_gaps: list[DataGap]
    non_claims: tuple[str, ...] = DATA_CATALOG_NON_CLAIMS
    execution_allowed: bool = False


@router.get("/data/sources", response_model=SourcesResponse)
async def list_sources(
    receipt_root: MarketDataReceiptRootDependency,
) -> SourcesResponse:
    """List known data sources from the registry."""
    view = build_data_catalog(receipt_root)
    return SourcesResponse(sources=view.sources)


@router.get("/data/catalog", response_model=CatalogListResponse)
async def list_catalog(
    receipt_root: MarketDataReceiptRootDependency,
) -> CatalogListResponse:
    """List all catalog entries and data gaps discovered from local receipts."""
    view = build_data_catalog(receipt_root)
    return CatalogListResponse(
        catalog_entries=view.catalog_entries,
        data_gaps=view.data_gaps,
        source_refs=view.source_refs,
    )


@router.get("/data/catalog/{dataset_key:path}", response_model=CatalogDetailResponse)
async def get_catalog(
    dataset_key: str,
    receipt_root: MarketDataReceiptRootDependency,
) -> CatalogDetailResponse:
    """Retrieve a single catalog entry by dataset key."""
    entry = get_catalog_entry(dataset_key, receipt_root)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"catalog entry not found: {dataset_key}")
    return CatalogDetailResponse(entry=entry)


@router.get("/data/gaps", response_model=GapsResponse)
async def list_gaps(
    receipt_root: MarketDataReceiptRootDependency,
) -> GapsResponse:
    """List all data gaps discovered from local receipts."""
    view = build_data_catalog(receipt_root)
    return GapsResponse(data_gaps=view.data_gaps)
