"""API routes for mandate-bound AgentAuthorityGrant credentials."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from finharness.api.dependencies import (
    EngineDependency,
    ReceiptRootDependency,
    WriteCapabilityDependency,
)
from finharness.statecore.agent_authority_grants import (
    AGENT_AUTHORITY_GRANT_NON_CLAIMS,
    AgentAuthorityGrantValidationError,
    AgentAuthorityGrantValidationResult,
    list_agent_authority_grants,
    record_agent_authority_grant,
    validate_agent_authority_grant,
)
from finharness.statecore.models import AgentAuthorityGrant

router = APIRouter(tags=["agent-authority-grants"])


class AgentAuthorityGrantRequest(BaseModel):
    capital_mandate_id: str
    agent_id: str
    agent_profile_name: str | None = None
    grant_scope: dict[str, Any] = Field(default_factory=dict)
    issued_by: str
    issued_reason: str
    expires_at_utc: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    agent_authority_grant_id: str | None = None


class AgentAuthorityGrantWriteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_authority_grant: AgentAuthorityGrant
    receipt_ref: str
    non_claims: tuple[str, ...] = AGENT_AUTHORITY_GRANT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class AgentAuthorityGrantListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_authority_grants: list[AgentAuthorityGrant]
    execution_allowed: bool = False
    authority_transition: bool = False


class AgentAuthorityGrantValidateRequest(BaseModel):
    requested_scope: dict[str, Any] = Field(default_factory=dict)
    now_utc: str | None = None


@router.post("/agent-authority-grants", response_model=AgentAuthorityGrantWriteResponse)
async def post_agent_authority_grant(
    body: AgentAuthorityGrantRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write_capability: WriteCapabilityDependency,
) -> AgentAuthorityGrantWriteResponse:
    try:
        grant = record_agent_authority_grant(
            capital_mandate_id=body.capital_mandate_id,
            agent_id=body.agent_id,
            agent_profile_name=body.agent_profile_name,
            grant_scope=body.grant_scope,
            issued_by=body.issued_by,
            issued_reason=body.issued_reason,
            expires_at_utc=body.expires_at_utc,
            source_refs=body.source_refs,
            receipt_refs=body.receipt_refs,
            agent_authority_grant_id=body.agent_authority_grant_id,
            engine=engine,
            receipt_root=receipt_root,
        )
    except AgentAuthorityGrantValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"capital mandate not found: {exc.args[0]}",
        ) from exc
    return AgentAuthorityGrantWriteResponse(
        agent_authority_grant=grant,
        receipt_ref=grant.receipt_ref or "",
    )


@router.get("/agent-authority-grants", response_model=AgentAuthorityGrantListResponse)
async def get_agent_authority_grants(
    engine: EngineDependency,
    agent_id: str | None = Query(default=None),
) -> AgentAuthorityGrantListResponse:
    return AgentAuthorityGrantListResponse(
        agent_authority_grants=list_agent_authority_grants(
            engine=engine,
            agent_id=agent_id,
        ),
    )


@router.get("/agent-authority-grants/{grant_id}", response_model=AgentAuthorityGrant)
async def get_agent_authority_grant(
    grant_id: str,
    engine: EngineDependency,
) -> AgentAuthorityGrant:
    with Session(engine) as session:
        grant = session.get(AgentAuthorityGrant, grant_id)
    if grant is None:
        raise HTTPException(status_code=404, detail="AgentAuthorityGrant not found")
    return grant


@router.post(
    "/agent-authority-grants/{grant_id}/validate",
    response_model=AgentAuthorityGrantValidationResult,
)
async def post_agent_authority_grant_validate(
    grant_id: str,
    body: AgentAuthorityGrantValidateRequest,
    engine: EngineDependency,
) -> AgentAuthorityGrantValidationResult:
    try:
        return validate_agent_authority_grant(
            grant_id,
            engine=engine,
            requested_scope=body.requested_scope,
            now_utc=body.now_utc,
        )
    except AgentAuthorityGrantValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
