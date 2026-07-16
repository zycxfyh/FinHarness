"""Read/write API routes for CapitalMandate policy domains."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from finharness.api.dependencies import (
    EngineDependency,
    OptionalOperatorDependency,
    ReceiptRootDependency,
    WriteCapabilityDependency,
)
from finharness.identity import (
    IdentityMutationClaim,
    IdentityMutationError,
    bind_authenticated_actor_to_mutation,
)
from finharness.statecore.capital_mandates import (
    CAPITAL_MANDATE_NON_CLAIMS,
    CapitalMandateKillSwitchScope,
    CapitalMandateLimits,
    CapitalMandateValidationError,
    ResolvedCapitalMandate,
    record_capital_mandate,
    resolve_capital_mandate,
    resume_capital_mandate,
    revoke_capital_mandate,
    suspend_capital_mandate,
)
from finharness.statecore.models import CapitalMandate

router = APIRouter(tags=["capital-mandates"])


class CapitalMandateCurrentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    available: bool
    capital_mandate: CapitalMandate | None
    resolution: ResolvedCapitalMandate | None = None
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
    model_config = ConfigDict(extra="forbid")

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
    human_reason: str
    explicit_confirmation: bool = False
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    capital_mandate_id: str | None = None
    typed_limits: CapitalMandateLimits = Field(default_factory=CapitalMandateLimits)
    kill_switch_scope: CapitalMandateKillSwitchScope = Field(
        default_factory=CapitalMandateKillSwitchScope
    )
    effective_at_utc: str | None = None
    expires_at_utc: str | None = None


class CapitalMandateLifecycleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    effective_at_utc: str | None = None


class CapitalMandateLifecycleResponse(BaseModel):
    resolution: ResolvedCapitalMandate
    receipt_ref: str
    execution_allowed: bool = False
    authority_transition: bool = False


@router.post("/capital-mandates", response_model=CapitalMandateWriteResponse)
async def post_capital_mandate(
    body: CapitalMandateRequest,
    http_request: Request,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    operator: WriteCapabilityDependency,
) -> CapitalMandateWriteResponse:
    raw_claim = getattr(http_request.state, "identity_mutation_claim", None)
    if raw_claim is not None and not isinstance(raw_claim, IdentityMutationClaim):
        raise HTTPException(status_code=409, detail="invalid authenticated actor claim")
    try:
        actor_binding = bind_authenticated_actor_to_mutation(
            raw_claim,
            context=operator,
        )
    except IdentityMutationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    actor_receipt_ref = actor_binding[0] if actor_binding is not None else None
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
            human_attester=operator.authoritative_actor_id,
            human_reason=body.human_reason,
            explicit_confirmation=body.explicit_confirmation,
            source_refs=body.source_refs,
            receipt_refs=body.receipt_refs,
            capital_mandate_id=body.capital_mandate_id,
            principal_id=operator.principal.principal_id,
            typed_limits=body.typed_limits,
            kill_switch_scope=body.kill_switch_scope,
            effective_at_utc=body.effective_at_utc,
            expires_at_utc=body.expires_at_utc,
            authenticated_actor_receipt_ref=actor_receipt_ref,
            legacy_actor_label=operator.principal.legacy_label,
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
    operator: OptionalOperatorDependency,
) -> CapitalMandateCurrentResponse:
    if operator is None:
        return CapitalMandateCurrentResponse(available=False, capital_mandate=None)
    resolution = resolve_capital_mandate(
        principal_id=operator.principal.principal_id,
        engine=engine,
    )
    mandate = None
    if resolution.version is not None:
        with Session(engine) as session:
            mandate = session.get(CapitalMandate, resolution.version.capital_mandate_id)
    return CapitalMandateCurrentResponse(
        available=resolution.status == "active",
        capital_mandate=mandate,
        resolution=resolution,
    )


@router.post(
    "/capital-mandates/{capital_mandate_id}/suspend",
    response_model=CapitalMandateLifecycleResponse,
)
async def post_suspend_capital_mandate(
    capital_mandate_id: str,
    body: CapitalMandateLifecycleRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    operator: WriteCapabilityDependency,
) -> CapitalMandateLifecycleResponse:
    return _apply_lifecycle_command(
        "suspend",
        capital_mandate_id=capital_mandate_id,
        body=body,
        engine=engine,
        receipt_root=receipt_root,
        principal_id=operator.principal.principal_id,
    )


@router.post(
    "/capital-mandates/{capital_mandate_id}/resume",
    response_model=CapitalMandateLifecycleResponse,
)
async def post_resume_capital_mandate(
    capital_mandate_id: str,
    body: CapitalMandateLifecycleRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    operator: WriteCapabilityDependency,
) -> CapitalMandateLifecycleResponse:
    return _apply_lifecycle_command(
        "resume",
        capital_mandate_id=capital_mandate_id,
        body=body,
        engine=engine,
        receipt_root=receipt_root,
        principal_id=operator.principal.principal_id,
    )


@router.post(
    "/capital-mandates/{capital_mandate_id}/revoke",
    response_model=CapitalMandateLifecycleResponse,
)
async def post_revoke_capital_mandate(
    capital_mandate_id: str,
    body: CapitalMandateLifecycleRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    operator: WriteCapabilityDependency,
) -> CapitalMandateLifecycleResponse:
    return _apply_lifecycle_command(
        "revoke",
        capital_mandate_id=capital_mandate_id,
        body=body,
        engine=engine,
        receipt_root=receipt_root,
        principal_id=operator.principal.principal_id,
    )


def _apply_lifecycle_command(
    command: str,
    *,
    capital_mandate_id: str,
    body: CapitalMandateLifecycleRequest,
    engine: Any,
    receipt_root: Any,
    principal_id: str,
) -> CapitalMandateLifecycleResponse:
    commands = {
        "suspend": suspend_capital_mandate,
        "resume": resume_capital_mandate,
        "revoke": revoke_capital_mandate,
    }
    try:
        event = commands[command](
            capital_mandate_id,
            principal_id=principal_id,
            actor_principal_id=principal_id,
            reason=body.reason,
            engine=engine,
            receipt_root=receipt_root,
            effective_at_utc=body.effective_at_utc,
        )
        resolution = resolve_capital_mandate(
            principal_id=principal_id,
            engine=engine,
            at_utc=event.effective_at_utc,
        )
    except CapitalMandateValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return CapitalMandateLifecycleResponse(
        resolution=resolution,
        receipt_ref=event.receipt_ref,
    )


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
