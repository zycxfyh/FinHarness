"""Read/write API routes for the Investment Policy Statement (L3)."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from finharness.api.dependencies import EngineDependency, ReceiptRootDependency, WriteCapabilityDependency
from finharness.exposure import compute_exposure
from finharness.ips import (
    IPS_NON_CLAIMS,
    IpsCheckReport,
    check_ips_compliance,
    current_ips,
    record_ips,
)
from finharness.statecore.models import InvestmentPolicyStatement

router = APIRouter(tags=["ips"])


class IpsCurrentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    available: bool
    ips: InvestmentPolicyStatement | None
    non_claims: tuple[str, ...] = IPS_NON_CLAIMS
    execution_allowed: bool = False


class IpsDraftRequest(BaseModel):
    liquidity_floor_months: Decimal = Field(gt=0)
    max_single_holding_pct: Decimal = Field(gt=0, le=1)
    cash_overweight_pct: Decimal | None = Field(default=None, gt=0, le=1)
    high_interest_rate_pct: Decimal | None = Field(default=None, gt=0, le=1)
    base_currency: str = "USD"
    allowed_asset_classes: list[str] = Field(default_factory=list)
    restricted_actions: list[str] = Field(default_factory=list)
    review_cadence: str = ""
    source_refs: list[str] = Field(default_factory=list)


@router.get("/ips/current", response_model=IpsCurrentResponse)
async def get_current_ips(engine: EngineDependency) -> IpsCurrentResponse:
    ips = current_ips(engine)
    return IpsCurrentResponse(available=ips is not None, ips=ips)


@router.post("/ips/draft", response_model=InvestmentPolicyStatement)
async def post_ips_draft(
    body: IpsDraftRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    write_capability: WriteCapabilityDependency,
) -> InvestmentPolicyStatement:
    return record_ips(
        liquidity_floor_months=body.liquidity_floor_months,
        max_single_holding_pct=body.max_single_holding_pct,
        cash_overweight_pct=body.cash_overweight_pct,
        high_interest_rate_pct=body.high_interest_rate_pct,
        base_currency=body.base_currency,
        allowed_asset_classes=body.allowed_asset_classes,
        restricted_actions=body.restricted_actions,
        review_cadence=body.review_cadence,
        source_refs=body.source_refs,
        engine=engine,
        receipt_root=receipt_root,
    )


@router.get("/ips/check", response_model=IpsCheckReport)
async def get_ips_check(engine: EngineDependency) -> IpsCheckReport:
    ips = current_ips(engine)
    if ips is None:
        raise HTTPException(
            status_code=404,
            detail="No active IPS; set one via POST /ips/draft before checking compliance.",
        )
    report = compute_exposure(engine)
    return check_ips_compliance(report, ips)
