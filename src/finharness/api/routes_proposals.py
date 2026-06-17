"""Governed proposal and human-attestation API routes."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from finharness.api.dependencies import EngineDependency, ReceiptRootDependency
from finharness.statecore.models import Attestation, Proposal
from finharness.statecore.proposals import (
    create_governed_attestation,
    create_governed_proposal,
)
from finharness.statecore.store import StateCoreStoreError

router = APIRouter(tags=["proposals"])

DecisionInput = Literal["approved", "rejected"]


class ProposalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    claim: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    limitations: dict[str, Any] = Field(default_factory=dict)
    non_claims: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("kind", "claim")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("proposal kind and claim are required")
        return value


class ProposalCreateResponse(BaseModel):
    proposal: Proposal
    receipt_ref: str
    execution_allowed: bool = False


class AttestationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: DecisionInput
    attester: str
    reason: str
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("attester", "reason")
    @classmethod
    def require_human_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("attestation requires a named human and written reason")
        return value


class AttestationCreateResponse(BaseModel):
    attestation: Attestation
    proposal: Proposal
    receipt_ref: str
    approved_is_not_execution_authorization: bool = True
    execution_allowed: bool = False


@router.post("/proposals", response_model=ProposalCreateResponse)
def create_proposal(
    request: ProposalCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ProposalCreateResponse:
    try:
        result = create_governed_proposal(
            kind=request.kind.strip(),
            claim=request.claim.strip(),
            evidence=request.evidence,
            assumptions=request.assumptions,
            limitations=request.limitations,
            non_claims=request.non_claims,
            source_refs=list(request.source_refs),
            engine=engine,
            receipt_root=receipt_root,
        )
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ProposalCreateResponse(
        proposal=result.proposal,
        receipt_ref=result.receipt_ref,
        execution_allowed=False,
    )


@router.post("/proposals/{proposal_id}/attest", response_model=AttestationCreateResponse)
def attest_proposal(
    proposal_id: str,
    request: AttestationCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> AttestationCreateResponse:
    try:
        result = create_governed_attestation(
            proposal_id=proposal_id,
            decision=request.decision,
            attester=request.attester.strip(),
            reason=request.reason.strip(),
            source_refs=list(request.source_refs),
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"proposal not found: {proposal_id}",
        ) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return AttestationCreateResponse(
        attestation=result.attestation,
        proposal=result.proposal,
        receipt_ref=result.receipt_ref,
        approved_is_not_execution_authorization=True,
        execution_allowed=False,
    )
