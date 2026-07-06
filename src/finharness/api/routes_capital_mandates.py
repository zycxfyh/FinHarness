"""Read/write API routes for CapitalMandate policy domains."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from finharness.api.dependencies import EngineDependency, ReceiptRootDependency, WriteCapabilityDependency
from finharness.statecore.capital_mandates import (
    CAPITAL_MANDATE_NON_CLAIMS,
    CapitalMandateValidationError,
    current_capital_mandate,
    record_capital_mandate,
)
from finharness.statecore.models import CapitalMandate

router = APIRouter(tags=["capital-mandates"])


class CapitalMandateCurrentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    available: bool
    capital_mandate: CapitalMandate | None
    non_claims: tuple[str, ...] = CAPITAL_MANDATE_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class CapitalMandateWriteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    capital_mandate: CapitalMandate
    receipt_ref: str
    non_claims: tuple[str, ...] = CAPITAL_MANDATE_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class CapitalMandateRequest(BaseModel):
    profile_snapshot: dict[str, Any] = Field(default_factory=dict)
    investment_objectives: dict[str, Any] = Field(default_factory=dict)
    risk_profile: dict[str, Any] = Field(default_factory=dict)
    allowed_asset_classes: list[str] = Field(default_factory=list)
    restricted_asset_classes: list[str] = Field(default_factory=list)
    allowed_action_types: list[str] = Field(default_factory=list)
    restricted_action_types: list[str] = Field(default_factory=list)
    autonomy_level: str = "L1_candidate_only"
    limit_book: dict[str, Any] = Field(default_factory=dict)
    kill_switch_rules: list[dict[str, Any]] = Field(default_factory=list)
    review_cadence: dict[str, Any] = Field(default_factory=dict)
    source_ips_id: str | None = None
    human_attester: str
    human_reason: str
    explicit_confirmation: bool = False
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    capital_mandate_id: str | None = None


@router.post("/capital-mandates", response_model=CapitalMandateWriteResponse)
async def post_capital_mandate(
    body: CapitalMandateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    write_capability: WriteCapabilityDependency,
) -> CapitalMandateWriteResponse:
    try:
        mandate = record_capital_mandate(
            profile_snapshot=body.profile_snapshot,
            investment_objectives=body.investment_objectives,
            risk_profile=body.risk_profile,
            allowed_asset_classes=body.allowed_asset_classes,
            restricted_asset_classes=body.restricted_asset_classes,
            allowed_action_types=body.allowed_action_types,
            restricted_action_types=body.restricted_action_types,
            autonomy_level=body.autonomy_level,
            limit_book=body.limit_book,
            kill_switch_rules=body.kill_switch_rules,
            review_cadence=body.review_cadence,
            source_ips_id=body.source_ips_id,
            human_attester=body.human_attester,
            human_reason=body.human_reason,
            explicit_confirmation=body.explicit_confirmation,
            source_refs=body.source_refs,
            receipt_refs=body.receipt_refs,
            capital_mandate_id=body.capital_mandate_id,
            engine=engine,
            receipt_root=receipt_root,
        )
    except (CapitalMandateValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"source IPS not found: {exc.args[0]}") from exc
    receipt_ref = mandate.receipt_ref or ""
    return CapitalMandateWriteResponse(capital_mandate=mandate, receipt_ref=receipt_ref)


@router.get("/capital-mandates/current", response_model=CapitalMandateCurrentResponse)
async def get_current_capital_mandate(
    engine: EngineDependency,
) -> CapitalMandateCurrentResponse:
    mandate = current_capital_mandate(engine)
    return CapitalMandateCurrentResponse(available=mandate is not None, capital_mandate=mandate)


@router.get("/capital-mandates/{capital_mandate_id}", response_model=CapitalMandate)
async def get_capital_mandate(
    capital_mandate_id: str,
    engine: EngineDependency,
) -> CapitalMandate:
    with Session(engine) as session:
        mandate = session.get(CapitalMandate, capital_mandate_id)
    if mandate is None:
        raise HTTPException(status_code=404, detail="CapitalMandate not found")
    return mandate
