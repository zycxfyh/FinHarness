"""Read-only data quality API routes.

Exposes quality reports and data gaps as dedicated API endpoints.
All endpoints are GET-only. No network calls. No write operations.
Reuses DataQualityReport from #105 and DataGap from #104.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from finharness.api.dependencies import MarketDataReceiptRootDependency
from finharness.data_catalog import build_data_catalog, get_catalog_entry
from finharness.data_quality_policy import DataQualityReport

router = APIRouter(tags=["data"])

DATA_QUALITY_NON_CLAIMS = (
    "Read-only data quality surface.",
    "No network calls triggered.",
    "No execution authorization.",
    "No provider fetch or refresh.",
)


def _entry_to_quality_report(entry) -> DataQualityReport:
    """Construct a DataQualityReport from a DataCatalogEntry."""
    return DataQualityReport(
        report_id=f"qr_{entry.dataset_key.replace('/', '_')}",
        dataset_key=entry.dataset_key,
        as_of_utc=entry.latest_as_of_utc,
        latest_receipt_ref=entry.latest_receipt_ref,
        freshness_status=entry.freshness_status,
        quality_status=entry.quality_status,
        reconciliation_status=entry.reconciliation_status,
        bias_status=entry.bias_status,
        readiness_status=entry.readiness_status,
        findings=list(entry.findings),
        blocks=list(entry.blocks),
    )


class DataQualityListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    reports: list[DataQualityReport]
    data_gaps: list
    source_refs: tuple[str, ...]
    non_claims: tuple[str, ...] = DATA_QUALITY_NON_CLAIMS
    execution_allowed: bool = False


class DataQualityDetailResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    report: DataQualityReport
    source_refs: tuple[str, ...]
    non_claims: tuple[str, ...] = DATA_QUALITY_NON_CLAIMS
    execution_allowed: bool = False


class DataGapsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_gaps: list
    severity_filter: str | None = None
    blocks_filter: str | None = None
    non_claims: tuple[str, ...] = DATA_QUALITY_NON_CLAIMS
    execution_allowed: bool = False


@router.get("/data/quality", response_model=DataQualityListResponse)
async def list_quality(
    receipt_root: MarketDataReceiptRootDependency,
) -> DataQualityListResponse:
    """List all quality reports and data gaps."""
    view = build_data_catalog(receipt_root)
    reports = [_entry_to_quality_report(entry) for entry in view.catalog_entries]
    gaps = view.data_gaps
    return DataQualityListResponse(
        reports=reports,
        data_gaps=gaps,
        source_refs=view.source_refs,
    )


@router.get("/data/quality/{dataset_key:path}", response_model=DataQualityDetailResponse)
async def get_quality(
    dataset_key: str,
    receipt_root: MarketDataReceiptRootDependency,
) -> DataQualityDetailResponse:
    """Retrieve a single quality report by dataset key."""
    entry = get_catalog_entry(dataset_key, receipt_root)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"dataset not found: {dataset_key}")
    report = _entry_to_quality_report(entry)
    return DataQualityDetailResponse(
        report=report,
        source_refs=(entry.latest_receipt_ref,),
    )


@router.get("/data/gaps", response_model=DataGapsResponse)
async def list_gaps_filtered(
    receipt_root: MarketDataReceiptRootDependency,
    severity: Annotated[str | None, Query(description="Filter by severity")] = None,
    blocks: Annotated[str | None, Query(description="Filter by blocked workflow")] = None,
) -> DataGapsResponse:
    """List data gaps with optional severity and blocks filters."""
    view = build_data_catalog(receipt_root)
    gaps = list(view.data_gaps)

    if severity is not None:
        gaps = [g for g in gaps if g.severity == severity]
    if blocks is not None:
        gaps = [g for g in gaps if blocks in g.blocks]

    return DataGapsResponse(
        data_gaps=gaps,
        severity_filter=severity,
        blocks_filter=blocks,
    )
