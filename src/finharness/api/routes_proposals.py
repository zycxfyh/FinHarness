"""Governed proposal and human-attestation API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import desc
from sqlmodel import Session, select

from finharness.api.dependencies import EngineDependency, ReceiptRootDependency
from finharness.market_data import ROOT
from finharness.review_read import read_proposal_timeline
from finharness.statecore.decision_scaffold import DecisionScaffoldError
from finharness.statecore.models import Attestation, Proposal, ReviewEvent
from finharness.statecore.proposal_revisions import walk_proposal_revisions
from finharness.statecore.proposals import (
    ReviewEventKind,
    archived_proposal_ids,
    create_governed_attestation,
    create_governed_proposal,
    create_governed_review_event,
    revise_governed_proposal_scaffold,
)
from finharness.statecore.risk_classification import HighRiskConfirmationError
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
    decision_scaffold: dict[str, Any] = Field(default_factory=dict)

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


class ProposalReviewResponse(BaseModel):
    proposal: Proposal
    attestations: list[Attestation]
    open_for_review: bool
    non_claims: tuple[str, ...] = (
        "Proposal is review evidence only.",
        "Human attestation is not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


class ProposalRevision(BaseModel):
    receipt_id: str
    receipt_ref: str
    created_at_utc: str
    content_hash: str | None = None
    supersedes: str | None = None
    proposal: dict[str, Any] = Field(default_factory=dict)
    execution_allowed: bool = False


class ProposalRevisionResponse(BaseModel):
    proposal_id: str
    revisions: list[ProposalRevision]
    non_claims: tuple[str, ...] = (
        "Proposal revisions are historical evidence only.",
        "Revision history is not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


class ProposalScaffoldRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attester: str
    reason: str
    decision_scaffold: dict[str, Any]
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("attester", "reason")
    @classmethod
    def require_human_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("proposal scaffold revision requires a named human and written reason")
        return value


class ProposalScaffoldRevisionResponse(BaseModel):
    proposal: Proposal
    receipt_ref: str
    previous_receipt_ref: str | None
    changed_scaffold_fields: tuple[str, ...]
    non_claims: tuple[str, ...] = (
        "Proposal scaffold revisions are historical review evidence.",
        "Counter-evidence enables human confirmation checks; it is not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


def _proposal_attestations(
    proposal_id: str,
    *,
    session: Session,
) -> list[Attestation]:
    return list(
        session.exec(
            select(Attestation)
            .where(Attestation.proposal_id == proposal_id)
            .order_by(desc(Attestation.created_at_utc), desc(Attestation.attestation_id))
        ).all()
    )


# Anomaly codes from the shared walker default to a 500 (a corrupt chain is a
# server-side data problem); these are the exceptions surfaced as 404.
_REVISION_ANOMALY_STATUS: dict[str, int] = {
    "missing": 404,
    "outside_allowed_roots": 404,
}


def _proposal_revision_chain(
    proposal: Proposal,
    *,
    receipt_root: Path,
    max_revisions: int = 100,
) -> list[ProposalRevision]:
    walk = walk_proposal_revisions(
        proposal.proposal_id,
        proposal.receipt_ref,
        allowed_roots=(ROOT.resolve(), receipt_root.resolve()),
        max_revisions=max_revisions,
    )
    for anomaly in walk.anomalies:
        if anomaly.code == "no_receipt_ref":
            # No receipt yet just means no history to show, not an error.
            continue
        raise HTTPException(
            status_code=_REVISION_ANOMALY_STATUS.get(anomaly.code, 500),
            detail=anomaly.detail,
        )
    return [
        ProposalRevision(
            receipt_id=record.receipt_id,
            receipt_ref=record.receipt_ref,
            created_at_utc=record.created_at_utc,
            content_hash=record.content_hash,
            supersedes=record.supersedes,
            proposal=record.proposal,
            execution_allowed=False,
        )
        for record in walk.revisions
    ]


@router.get("/proposals", response_model=list[ProposalReviewResponse])
async def list_proposals(
    engine: EngineDependency,
    status: Annotated[Literal["all", "open", "attested"], Query()] = "all",
    archive: Annotated[Literal["all", "active", "archived"], Query()] = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ProposalReviewResponse]:
    # `archive` defaults to "all": the legacy response (contents + shape) is unchanged.
    # Only an explicit archive=active|archived hides/keeps archived proposals; archive
    # events never silently change the default list.
    with Session(engine) as session:
        proposals = list(
            session.exec(
                select(Proposal)
                .order_by(desc(Proposal.created_at_utc), desc(Proposal.proposal_id))
                .limit(limit)
            ).all()
        )
        responses: list[ProposalReviewResponse] = []
        for proposal in proposals:
            attestations = _proposal_attestations(proposal.proposal_id, session=session)
            responses.append(
                ProposalReviewResponse(
                    proposal=proposal,
                    attestations=attestations,
                    open_for_review=not attestations,
                    execution_allowed=False,
                )
            )
    if status == "open":
        responses = [response for response in responses if response.open_for_review]
    elif status == "attested":
        responses = [response for response in responses if not response.open_for_review]
    if archive != "all":
        archived = archived_proposal_ids(engine)
        if archive == "active":
            responses = [r for r in responses if r.proposal.proposal_id not in archived]
        else:  # archived
            responses = [r for r in responses if r.proposal.proposal_id in archived]
    return responses


@router.get("/proposals/{proposal_id}", response_model=ProposalReviewResponse)
async def get_proposal(proposal_id: str, engine: EngineDependency) -> ProposalReviewResponse:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        if proposal is None:
            raise HTTPException(
                status_code=404,
                detail=f"proposal not found: {proposal_id}",
            )
        attestations = _proposal_attestations(proposal_id, session=session)
    return ProposalReviewResponse(
        proposal=proposal,
        attestations=attestations,
        open_for_review=not attestations,
        execution_allowed=False,
    )


@router.get("/proposals/{proposal_id}/revisions", response_model=ProposalRevisionResponse)
async def get_proposal_revisions(
    proposal_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ProposalRevisionResponse:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail=f"proposal not found: {proposal_id}",
        )
    return ProposalRevisionResponse(
        proposal_id=proposal.proposal_id,
        revisions=_proposal_revision_chain(proposal, receipt_root=receipt_root),
        execution_allowed=False,
    )


@router.patch(
    "/proposals/{proposal_id}/decision-scaffold",
    response_model=ProposalScaffoldRevisionResponse,
)
async def revise_proposal_decision_scaffold(
    proposal_id: str,
    request: ProposalScaffoldRevisionRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ProposalScaffoldRevisionResponse:
    try:
        result = revise_governed_proposal_scaffold(
            proposal_id=proposal_id,
            scaffold_patch=request.decision_scaffold,
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
    except (DecisionScaffoldError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ProposalScaffoldRevisionResponse(
        proposal=result.proposal,
        receipt_ref=result.receipt_ref,
        previous_receipt_ref=result.previous_receipt_ref,
        changed_scaffold_fields=result.changed_scaffold_fields,
        execution_allowed=False,
    )


@router.post("/proposals", response_model=ProposalCreateResponse)
async def create_proposal(
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
            decision_scaffold=request.decision_scaffold,
            engine=engine,
            receipt_root=receipt_root,
        )
    except DecisionScaffoldError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ProposalCreateResponse(
        proposal=result.proposal,
        receipt_ref=result.receipt_ref,
        execution_allowed=False,
    )


@router.post("/proposals/{proposal_id}/attest", response_model=AttestationCreateResponse)
async def attest_proposal(
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
    except HighRiskConfirmationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return AttestationCreateResponse(
        attestation=result.attestation,
        proposal=result.proposal,
        receipt_ref=result.receipt_ref,
        approved_is_not_execution_authorization=True,
        execution_allowed=False,
    )


class TimelineEntry(BaseModel):
    source_type: Literal["attestation", "review_event"]
    id: str
    kind: str
    created_at_utc: str
    attester: str
    reason: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ProposalTimelineResponse(BaseModel):
    proposal_id: str
    is_archived: bool
    entries: list[TimelineEntry]
    non_claims: tuple[str, ...] = (
        "Review timeline is historical evidence only.",
        "Annotations and archive actions are not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


class ReviewEventCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ReviewEventKind
    attester: str
    reason: str
    text: str | None = None
    attestation_ref: str | None = None
    compare_with: str | None = None
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("attester", "reason")
    @classmethod
    def require_human_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("review event requires a named human and written reason")
        return value


class ReviewEventCreateResponse(BaseModel):
    review_event: ReviewEvent
    receipt_ref: str
    execution_allowed: bool = False


@router.get("/proposals/{proposal_id}/timeline", response_model=ProposalTimelineResponse)
async def get_proposal_timeline(
    proposal_id: str, engine: EngineDependency
) -> ProposalTimelineResponse:
    """Read-only merged review timeline: attestations + review events, newest first.

    Thin adapter over the Review-System read model (review_read). Attestation stays the
    decision of record; review events are the interaction ledger."""
    timeline = read_proposal_timeline(engine, proposal_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail=f"proposal not found: {proposal_id}")
    return ProposalTimelineResponse(
        proposal_id=timeline.proposal_id,
        is_archived=timeline.is_archived,
        entries=[
            TimelineEntry(
                source_type=entry.source_type,
                id=entry.id,
                kind=entry.kind,
                created_at_utc=entry.created_at_utc,
                attester=entry.attester,
                reason=entry.reason,
                detail=entry.detail,
            )
            for entry in timeline.entries
        ],
        execution_allowed=False,
    )


@router.post(
    "/proposals/{proposal_id}/review-events", response_model=ReviewEventCreateResponse
)
async def add_review_event(
    proposal_id: str,
    request: ReviewEventCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ReviewEventCreateResponse:
    try:
        result = create_governed_review_event(
            proposal_id=proposal_id,
            kind=request.kind,
            attester=request.attester.strip(),
            reason=request.reason.strip(),
            text=request.text,
            attestation_ref=request.attestation_ref,
            compare_with=request.compare_with,
            source_refs=list(request.source_refs),
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"proposal not found: {proposal_id}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ReviewEventCreateResponse(
        review_event=result.review_event,
        receipt_ref=result.receipt_ref,
        execution_allowed=False,
    )
