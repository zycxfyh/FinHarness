"""Governed proposal and human-attestation API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session

from finharness.api.dependencies import EngineDependency, ReceiptRootDependency
from finharness.market_data import ROOT
from finharness.statecore.models import Attestation, Proposal, ReceiptIndex
from finharness.statecore.receipt_io import atomic_write_json, remove_file_best_effort
from finharness.statecore.store import StateCoreStoreError, write_records

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


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _receipt_index(
    *,
    receipt_id: str,
    kind: str,
    path: Path,
    created_at_utc: str,
    refs: list[str],
) -> ReceiptIndex:
    display = _display_path(path)
    return ReceiptIndex(
        receipt_id=receipt_id,
        kind=kind,
        path=display,
        created_at_utc=created_at_utc,
        source_refs=[display],
        refs=refs,
    )


def _proposal_receipt_payload(proposal: Proposal, receipt_id: str) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "state_core_proposal",
        "created_at_utc": proposal.created_at_utc,
        "proposal": proposal.model_dump(mode="json"),
        "governance": {
            "execution_allowed": False,
            "human_review_required": True,
            "not_execution_authorization": True,
            "not_investment_advice": True,
            "non_claims": [
                "This proposal is not trading authorization.",
                "This proposal cannot place orders or transfer funds.",
                "Any approval records human review only.",
            ],
        },
    }


def _attestation_receipt_payload(
    attestation: Attestation,
    proposal: Proposal,
    receipt_id: str,
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "state_core_attestation",
        "created_at_utc": attestation.created_at_utc,
        "proposal_id": proposal.proposal_id,
        "proposal_receipt_ref": proposal.receipt_ref,
        "attestation": attestation.model_dump(mode="json"),
        "governance": {
            "execution_allowed": False,
            "approved_is_not_execution_authorization": True,
            "not_execution_authorization": True,
            "not_investment_advice": True,
        },
    }


@router.post("/proposals", response_model=ProposalCreateResponse)
def create_proposal(
    request: ProposalCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ProposalCreateResponse:
    created_at = _now_utc()
    proposal_id = _safe_id(f"prop_{_stamp()}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{proposal_id}"
    receipt_path = receipt_root / "proposals" / f"{receipt_id}.json"
    receipt_ref = _display_path(receipt_path)
    proposal = Proposal(
        proposal_id=proposal_id,
        kind=request.kind.strip(),
        claim=request.claim.strip(),
        evidence=request.evidence,
        assumptions=request.assumptions,
        limitations=request.limitations,
        non_claims=[
            *request.non_claims,
            "Not execution authorization.",
            "Not investment advice.",
        ],
        source_refs=list(request.source_refs),
        execution_allowed=False,
        receipt_ref=receipt_ref,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    receipt_payload = _proposal_receipt_payload(proposal, receipt_id)
    atomic_write_json(receipt_path, receipt_payload)
    receipt_index = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_proposal",
        path=receipt_path,
        created_at_utc=created_at,
        refs=list(request.source_refs),
    )
    try:
        write_records([proposal, receipt_index], engine=engine)
    except StateCoreStoreError as exc:
        remove_file_best_effort(receipt_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ProposalCreateResponse(
        proposal=proposal,
        receipt_ref=receipt_ref,
        execution_allowed=False,
    )


@router.post("/proposals/{proposal_id}/attest", response_model=AttestationCreateResponse)
def attest_proposal(
    proposal_id: str,
    request: AttestationCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> AttestationCreateResponse:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"proposal not found: {proposal_id}")

    created_at = _now_utc()
    attestation_id = _safe_id(f"att_{_stamp()}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{attestation_id}"
    receipt_path = receipt_root / "attestations" / f"{receipt_id}.json"
    receipt_ref = _display_path(receipt_path)
    attestation = Attestation(
        attestation_id=attestation_id,
        proposal_id=proposal.proposal_id,
        attester=request.attester.strip(),
        reason=request.reason.strip(),
        decision=request.decision,
        source_refs=[
            ref
            for ref in [proposal.receipt_ref, receipt_ref, *request.source_refs]
            if ref
        ],
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    receipt_payload = _attestation_receipt_payload(
        attestation,
        proposal,
        receipt_id,
    )
    atomic_write_json(receipt_path, receipt_payload)
    receipt_index = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_attestation",
        path=receipt_path,
        created_at_utc=created_at,
        refs=[ref for ref in [proposal.receipt_ref, proposal.proposal_id] if ref],
    )
    try:
        write_records([attestation, receipt_index], engine=engine)
    except StateCoreStoreError as exc:
        remove_file_best_effort(receipt_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return AttestationCreateResponse(
        attestation=attestation,
        proposal=proposal,
        receipt_ref=receipt_ref,
        approved_is_not_execution_authorization=True,
        execution_allowed=False,
    )
