"""Governed proposal and human-attestation API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import desc
from sqlmodel import Session, select

from finharness.api.dependencies import (
    EngineDependency,
    ReceiptRootDependency,
    WriteCapabilityDependency,
)
from finharness.project_paths import ROOT
from finharness.proposal_queue_checks import (
    ProposalQueueChecks,
    build_proposal_queue_checks,
)
from finharness.review_read import read_proposal_timeline
from finharness.scaffold_candidate_preflight import (
    SCAFFOLD_CANDIDATE_PREFLIGHT_NON_CLAIMS,
    PreflightFinding,
    ScaffoldCandidatePreflightReport,
    find_scaffold_revision_candidate,
    preflight_scaffold_revision_candidate,
)
from finharness.statecore.decision_scaffold import DecisionScaffoldError
from finharness.statecore.models import Attestation, Proposal, ReviewEvent
from finharness.statecore.proposal_revisions import walk_proposal_revisions
from finharness.statecore.proposal_version import (
    CurrentProposalVersion,
    ProposalVersionResolutionError,
    require_current_proposal_version,
    resolve_current_proposal_version,
)
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

DecisionInput = Literal["approved", "rejected", "deferred"]


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
    # Optional only for compatibility with pre-version clients. The Cockpit always
    # supplies both; when either is supplied the pair is mandatory and stale-safe.
    expected_proposal_version_id: str | None = None
    expected_proposal_receipt_ref: str | None = None
    source_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "attester",
        "reason",
    )
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


class AttestationReviewView(BaseModel):
    attestation_id: str
    proposal_id: str
    attester: str
    reason: str
    decision: DecisionInput
    source_refs: list[str]
    authority_level: str
    created_at_utc: str
    bound_proposal_version_id: str | None
    bound_proposal_receipt_ref: str | None
    stale: bool


class AgentReviewSurface(BaseModel):
    created_by: Literal["agent"] = "agent"
    active_profile: str
    reason: str
    context_pack_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    receipt_ref: str
    review_state: Literal["pending_human_review", "human_attestation_recorded"]
    requires_human_review: bool = True
    execution_allowed: bool = False
    authority_transition: bool = False
    guardrails: dict[str, Any] = Field(
        default_factory=lambda: {
            "execution_allowed": False,
            "requires_human_review": True,
            "not_approval": True,
            "not_attestation": True,
            "not_execution_authorization": True,
        }
    )
    non_claims: tuple[str, ...] = (
        "Agent-created proposals are review drafts, not recommendations.",
        "Human review is required before any decision of record.",
        "Agent draft provenance is review metadata, not approval or execution.",
    )


class ProposalReviewResponse(BaseModel):
    proposal: Proposal
    attestations: list[AttestationReviewView]
    open_for_review: bool
    agent_review: AgentReviewSurface | None = None
    queue_checks: ProposalQueueChecks
    non_claims: tuple[str, ...] = (
        "Proposal is review evidence only.",
        "Human attestation is not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


ReviewTaskState = Literal[
    "ready_for_review",
    "needs_evidence",
    "blocked",
    "completed",
    "archived",
]


class EvidenceRequest(BaseModel):
    request_id: str
    code: str
    status: Literal["open"] = "open"
    message: str
    recovery_hint: str
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    blocked_transitions: tuple[str, ...] = ()
    execution_allowed: bool = False
    authority_transition: bool = False


class ReviewTaskLifecycle(BaseModel):
    task_id: str
    proposal_id: str
    state: ReviewTaskState
    created_by: Literal["agent", "human_or_system"]
    active_profile: str | None = None
    open_for_review: bool
    is_archived: bool
    queue_check_state: str
    block_codes: list[str] = Field(default_factory=list)
    blocked_transitions: tuple[str, ...] = ()
    evidence_requests: list[EvidenceRequest] = Field(default_factory=list)
    latest_event_kind: str | None = None
    latest_event_at_utc: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    context_pack_refs: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    execution_allowed: bool = False
    authority_transition: bool = False
    non_claims: tuple[str, ...] = (
        "Review task lifecycle is a read-only projection, not a new task write surface.",
        "Evidence requests are derived from queue checks; they are not approval.",
        "Review task state does not authorize execution.",
    )


class ProposalRevision(BaseModel):
    receipt_id: str
    receipt_ref: str
    created_at_utc: str
    content_hash: str | None = None
    supersedes: str | None = None
    proposal: dict[str, Any] = Field(default_factory=dict)
    revision_context: dict[str, Any] = Field(default_factory=dict)
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


class ScaffoldRevisionCandidateApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    human_attester: str
    human_reason: str
    expected_candidate_receipt_ref: str
    expected_proposal_receipt_ref: str
    expected_preflight_report_hash: str
    explicit_confirmation: bool
    explicit_preflight_acknowledgement: bool = False
    acknowledged_preflight_warning_codes: list[str] = Field(default_factory=list)

    @field_validator(
        "human_attester",
        "human_reason",
        "expected_candidate_receipt_ref",
        "expected_proposal_receipt_ref",
        "expected_preflight_report_hash",
    )
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "candidate apply requires non-blank human context, receipts, and preflight hash"
            )
        return value

    @field_validator("explicit_confirmation")
    @classmethod
    def require_explicit_confirmation(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("candidate apply requires explicit_confirmation=true")
        return True

    @field_validator("acknowledged_preflight_warning_codes")
    @classmethod
    def clean_warning_codes(cls, value: list[str]) -> list[str]:
        return sorted({str(item).strip() for item in value if str(item).strip()})


class ScaffoldRevisionCandidateApplyResponse(BaseModel):
    proposal: Proposal
    receipt_ref: str
    previous_receipt_ref: str | None
    changed_scaffold_fields: tuple[str, ...]
    applied_candidate_id: str
    candidate_receipt_ref: str
    candidate_review_event_id: str
    non_claims: tuple[str, ...] = (
        "Candidate apply is a human-confirmed scaffold revision, not Agent auto-apply.",
        "Applying scaffold text is not approval, attestation, or execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False
    authority_transition: bool = False


class ScaffoldCandidatePreflightFindingView(BaseModel):
    code: str
    severity: str
    message: str
    recovery_hint: str
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    blocks_apply: bool


class ScaffoldCandidatePreflightResponse(BaseModel):
    candidate_id: str
    proposal_id: str
    status: str
    system_preflight_recomputed: bool
    findings: list[ScaffoldCandidatePreflightFindingView]
    candidate_receipt_ref: str | None
    current_proposal_receipt_ref: str | None
    proposed_scaffold: dict[str, Any]
    changed_fields: list[str]
    basis_risk_ids: list[str]
    active_basis_risk_ids: list[str]
    missing_basis_risk_ids: list[str]
    source_refs: list[str]
    receipt_refs: list[str]
    report_hash: str
    non_claims: tuple[str, ...] = SCAFFOLD_CANDIDATE_PREFLIGHT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


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


def _scaffold_patch_from_candidate(
    *,
    event: ReviewEvent,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if payload.get("proposal_id") != event.proposal_id:
        raise ValueError("candidate payload proposal_id does not match review event")
    patch = payload.get("scaffold_patch")
    if not isinstance(patch, dict):
        raise ValueError("candidate payload scaffold_patch is not an object")
    return patch


def _preflight_finding_view(
    finding: PreflightFinding,
) -> ScaffoldCandidatePreflightFindingView:
    return ScaffoldCandidatePreflightFindingView(
        code=finding.code,
        severity=finding.severity,
        message=finding.message,
        recovery_hint=finding.recovery_hint,
        source_refs=finding.source_refs,
        receipt_refs=finding.receipt_refs,
        blocks_apply=finding.blocks_apply,
    )


def _preflight_warning_codes(findings: list[PreflightFinding]) -> set[str]:
    return {finding.code for finding in findings if not finding.blocks_apply}


def _enforce_scaffold_candidate_preflight_gate(
    candidate_id: str,
    *,
    request: ScaffoldRevisionCandidateApplyRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ScaffoldCandidatePreflightReport:
    preflight = preflight_scaffold_revision_candidate(
        candidate_id,
        engine=engine,
        receipt_root=receipt_root,
    )
    if preflight is None:
        raise HTTPException(
            status_code=404,
            detail=f"scaffold revision candidate not found: {candidate_id}",
        )
    if preflight.report_hash != request.expected_preflight_report_hash.strip():
        raise HTTPException(
            status_code=409,
            detail="preflight report hash does not match current system preflight",
        )
    if preflight.status == "block":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "preflight_blocked",
                "findings": [
                    _preflight_finding_view(finding).model_dump() for finding in preflight.findings
                ],
                "execution_allowed": False,
                "authority_transition": False,
            },
        )
    warning_codes = _preflight_warning_codes(preflight.findings)
    if warning_codes:
        acknowledged = set(request.acknowledged_preflight_warning_codes)
        if not request.explicit_preflight_acknowledgement:
            raise HTTPException(
                status_code=422,
                detail="preflight warnings require explicit acknowledgement",
            )
        if not warning_codes <= acknowledged:
            raise HTTPException(
                status_code=422,
                detail="not all preflight warnings acknowledged",
            )
    return preflight


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
            revision_context=record.revision_context,
            execution_allowed=False,
        )
        for record in walk.revisions
    ]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _agent_review_surface(
    proposal: Proposal,
    *,
    receipt_root: Path,
    open_for_review: bool,
) -> AgentReviewSurface | None:
    walk = walk_proposal_revisions(
        proposal.proposal_id,
        proposal.receipt_ref,
        allowed_roots=(ROOT.resolve(), receipt_root.resolve()),
        max_revisions=100,
    )
    for record in walk.revisions:
        context = record.revision_context
        if context.get("kind") != "agent_proposal_draft":
            continue
        return AgentReviewSurface(
            active_profile=str(context.get("profile") or "unknown"),
            reason=str(context.get("reason") or ""),
            context_pack_refs=_string_list(context.get("context_pack_refs")),
            source_refs=_string_list(record.proposal.get("source_refs")),
            receipt_ref=record.receipt_ref,
            review_state=(
                "pending_human_review" if open_for_review else "human_attestation_recorded"
            ),
            requires_human_review=True,
            execution_allowed=False,
            authority_transition=False,
        )
    return None


def _proposal_review_response(
    proposal: Proposal,
    attestations: list[Attestation],
    *,
    engine: EngineDependency,
    receipt_root: Path,
) -> ProposalReviewResponse:
    current = _resolve_proposal_version_for_api(
        proposal.proposal_id,
        engine=engine,
        receipt_root=receipt_root,
    )
    views = _attestation_review_views(attestations, current=current)
    open_for_review = not any(
        not attestation.stale and attestation.decision in {"approved", "rejected"}
        for attestation in views
    )
    agent_review = _agent_review_surface(
        proposal,
        receipt_root=receipt_root,
        open_for_review=open_for_review,
    )
    return ProposalReviewResponse(
        proposal=proposal,
        attestations=views,
        open_for_review=open_for_review,
        agent_review=agent_review,
        queue_checks=build_proposal_queue_checks(
            proposal,
            engine=engine,
            open_for_review=open_for_review,
            created_by="agent" if agent_review else "human_or_system",
            active_profile=agent_review.active_profile if agent_review else None,
            source_refs=list(proposal.source_refs),
            receipt_refs=[proposal.receipt_ref] if proposal.receipt_ref else [],
            context_pack_refs=agent_review.context_pack_refs if agent_review else [],
        ),
        execution_allowed=False,
    )


def _resolve_proposal_version_for_api(
    proposal_id: str,
    *,
    engine: EngineDependency,
    receipt_root: Path,
) -> CurrentProposalVersion:
    try:
        return resolve_current_proposal_version(
            proposal_id,
            engine=engine,
            receipt_root=receipt_root,
        )
    except ProposalVersionResolutionError as exc:
        status = 404 if exc.code == "proposal_not_found" else 409
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


def _attestation_review_views(
    attestations: list[Attestation],
    *,
    current: CurrentProposalVersion,
) -> list[AttestationReviewView]:
    lineage_by_receipt = {item.receipt_ref: item for item in current.lineage}
    views: list[AttestationReviewView] = []
    for attestation in attestations:
        bound = next(
            (
                lineage_by_receipt[ref]
                for ref in attestation.source_refs
                if ref in lineage_by_receipt
            ),
            None,
        )
        views.append(
            AttestationReviewView(
                **attestation.model_dump(mode="json"),
                bound_proposal_version_id=(
                    bound.proposal_version_id if bound is not None else None
                ),
                bound_proposal_receipt_ref=(bound.receipt_ref if bound is not None else None),
                stale=(bound is None or bound.proposal_version_id != current.proposal_version_id),
            )
        )
    return views


_EVIDENCE_REQUEST_CODES = {
    "missing_source_refs",
    "counter_evidence_needed",
    "data_gap",
    "stale_context",
    "policy_mismatch",
}


def _review_task_lifecycle(
    review: ProposalReviewResponse,
    *,
    timeline: ProposalTimelineResponse,
) -> ReviewTaskLifecycle:
    queue_checks = review.queue_checks
    evidence_requests = [
        EvidenceRequest(
            request_id=f"evidence_request:{review.proposal.proposal_id}:{finding.code}",
            code=finding.code,
            message=finding.message,
            recovery_hint=finding.recovery_hint,
            source_refs=list(finding.source_refs),
            receipt_refs=list(finding.receipt_refs),
            blocked_transitions=tuple(finding.blocked_transitions),
            execution_allowed=False,
            authority_transition=False,
        )
        for finding in queue_checks.blocks
        if finding.code in _EVIDENCE_REQUEST_CODES
    ]
    latest = timeline.entries[0] if timeline.entries else None
    non_evidence_blocks = [
        finding.code
        for finding in queue_checks.blocks
        if finding.code not in _EVIDENCE_REQUEST_CODES and finding.code != "human_review_required"
    ]
    if timeline.is_archived:
        state: ReviewTaskState = "archived"
    elif not review.open_for_review:
        state = "completed"
    elif evidence_requests:
        state = "needs_evidence"
    elif non_evidence_blocks:
        state = "blocked"
    else:
        state = "ready_for_review"
    return ReviewTaskLifecycle(
        task_id=f"review_task:{review.proposal.proposal_id}",
        proposal_id=review.proposal.proposal_id,
        state=state,
        created_by=queue_checks.created_by,
        active_profile=queue_checks.active_profile,
        open_for_review=review.open_for_review,
        is_archived=timeline.is_archived,
        queue_check_state=queue_checks.check_state,
        block_codes=[finding.code for finding in queue_checks.blocks],
        blocked_transitions=queue_checks.blocked_transitions,
        evidence_requests=evidence_requests,
        latest_event_kind=latest.kind if latest else None,
        latest_event_at_utc=latest.created_at_utc if latest else None,
        source_refs=list(queue_checks.source_refs),
        receipt_refs=list(queue_checks.receipt_refs),
        context_pack_refs=list(queue_checks.context_pack_refs),
        requires_human_review=True,
        execution_allowed=False,
        authority_transition=False,
    )


@router.get("/proposals", response_model=list[ProposalReviewResponse])
async def list_proposals(
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
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
                _proposal_review_response(
                    proposal,
                    attestations,
                    engine=engine,
                    receipt_root=receipt_root,
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
async def get_proposal(
    proposal_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ProposalReviewResponse:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        if proposal is None:
            raise HTTPException(
                status_code=404,
                detail=f"proposal not found: {proposal_id}",
            )
        attestations = _proposal_attestations(proposal_id, session=session)
    return _proposal_review_response(
        proposal,
        attestations,
        engine=engine,
        receipt_root=receipt_root,
    )


@router.get(
    "/proposals/{proposal_id}/queue-checks",
    response_model=ProposalQueueChecks,
)
async def get_proposal_queue_checks(
    proposal_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ProposalQueueChecks:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        if proposal is None:
            raise HTTPException(
                status_code=404,
                detail=f"proposal not found: {proposal_id}",
            )
        attestations = _proposal_attestations(proposal_id, session=session)
    return _proposal_review_response(
        proposal,
        attestations,
        engine=engine,
        receipt_root=receipt_root,
    ).queue_checks


@router.get(
    "/proposals/{proposal_id}/review-task",
    response_model=ReviewTaskLifecycle,
)
async def get_proposal_review_task(
    proposal_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ReviewTaskLifecycle:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        if proposal is None:
            raise HTTPException(
                status_code=404,
                detail=f"proposal not found: {proposal_id}",
            )
        attestations = _proposal_attestations(proposal_id, session=session)
    timeline = read_proposal_timeline(engine, proposal_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail=f"proposal not found: {proposal_id}")
    review = _proposal_review_response(
        proposal,
        attestations,
        engine=engine,
        receipt_root=receipt_root,
    )
    return _review_task_lifecycle(
        review,
        timeline=ProposalTimelineResponse(
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
        ),
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
    _write_capability: WriteCapabilityDependency,
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


@router.get(
    "/scaffold-revision-candidates/{candidate_id}/preflight",
    response_model=ScaffoldCandidatePreflightResponse,
)
async def get_scaffold_revision_candidate_preflight(
    candidate_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ScaffoldCandidatePreflightResponse:
    report = preflight_scaffold_revision_candidate(
        candidate_id,
        engine=engine,
        receipt_root=receipt_root,
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"scaffold revision candidate not found: {candidate_id}",
        )
    return ScaffoldCandidatePreflightResponse(
        candidate_id=report.candidate_id,
        proposal_id=report.proposal_id,
        status=report.status,
        system_preflight_recomputed=report.system_preflight_recomputed,
        findings=[_preflight_finding_view(finding) for finding in report.findings],
        candidate_receipt_ref=report.candidate_receipt_ref,
        current_proposal_receipt_ref=report.current_proposal_receipt_ref,
        proposed_scaffold=report.proposed_scaffold,
        changed_fields=report.changed_fields,
        basis_risk_ids=report.basis_risk_ids,
        active_basis_risk_ids=report.active_basis_risk_ids,
        missing_basis_risk_ids=report.missing_basis_risk_ids,
        source_refs=report.source_refs,
        receipt_refs=report.receipt_refs,
        report_hash=report.report_hash,
        execution_allowed=False,
        authority_transition=False,
    )


@router.post(
    "/scaffold-revision-candidates/{candidate_id}/apply",
    response_model=ScaffoldRevisionCandidateApplyResponse,
)
async def apply_scaffold_revision_candidate(
    candidate_id: str,
    request: ScaffoldRevisionCandidateApplyRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write_capability: WriteCapabilityDependency,
) -> ScaffoldRevisionCandidateApplyResponse:
    candidate = find_scaffold_revision_candidate(candidate_id, engine=engine)
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail=f"scaffold revision candidate not found: {candidate_id}",
        )
    event = candidate.event
    payload = candidate.payload
    if payload is None:
        raise HTTPException(
            status_code=422,
            detail=candidate.payload_error or "candidate payload is not an object",
        )
    candidate_receipt_ref = candidate.candidate_receipt_ref
    if not candidate_receipt_ref:
        raise HTTPException(
            status_code=422,
            detail="candidate review event receipt ref is missing",
        )
    if request.expected_candidate_receipt_ref.strip() != candidate_receipt_ref:
        raise HTTPException(
            status_code=409,
            detail="candidate receipt ref does not match expected_candidate_receipt_ref",
        )
    with Session(engine) as session:
        proposal = session.get(Proposal, event.proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail=f"proposal not found: {event.proposal_id}",
        )
    if request.expected_proposal_receipt_ref.strip() != (proposal.receipt_ref or ""):
        raise HTTPException(
            status_code=409,
            detail="proposal receipt ref does not match expected_proposal_receipt_ref",
        )
    preflight = _enforce_scaffold_candidate_preflight_gate(
        candidate_id,
        request=request,
        engine=engine,
        receipt_root=receipt_root,
    )

    try:
        scaffold_patch = _scaffold_patch_from_candidate(event=event, payload=payload)
        result = revise_governed_proposal_scaffold(
            proposal_id=event.proposal_id,
            scaffold_patch=scaffold_patch,
            attester=request.human_attester.strip(),
            reason=request.human_reason.strip(),
            source_refs=[
                candidate_receipt_ref,
                request.expected_proposal_receipt_ref.strip(),
                *event.source_refs,
                *_string_list(payload.get("source_refs")),
                *_string_list(payload.get("receipt_refs")),
            ],
            revision_context_extra={
                "source": "agent_scaffold_revision_apply_candidate",
                "candidate_id": candidate_id,
                "candidate_review_event_id": event.review_event_id,
                "candidate_receipt_ref": candidate_receipt_ref,
                "expected_proposal_receipt_ref": request.expected_proposal_receipt_ref.strip(),
                "system_preflight_report_hash": preflight.report_hash,
                "system_preflight_status": preflight.status,
                "system_preflight_recomputed": True,
                "system_preflight_finding_codes": [finding.code for finding in preflight.findings],
                "acknowledged_preflight_warning_codes": (
                    request.acknowledged_preflight_warning_codes
                ),
                "human_confirmed": True,
                "explicit_confirmation": True,
                "explicit_preflight_acknowledgement": (request.explicit_preflight_acknowledgement),
                "authority_transition": False,
            },
            engine=engine,
            receipt_root=receipt_root,
        )
    except (DecisionScaffoldError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ScaffoldRevisionCandidateApplyResponse(
        proposal=result.proposal,
        receipt_ref=result.receipt_ref,
        previous_receipt_ref=result.previous_receipt_ref,
        changed_scaffold_fields=result.changed_scaffold_fields,
        applied_candidate_id=candidate_id,
        candidate_receipt_ref=candidate_receipt_ref,
        candidate_review_event_id=event.review_event_id,
        execution_allowed=False,
        authority_transition=False,
    )


@router.post("/proposals", response_model=ProposalCreateResponse)
async def create_proposal(
    request: ProposalCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write_capability: WriteCapabilityDependency,
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
    _write_capability: WriteCapabilityDependency,
) -> AttestationCreateResponse:
    try:
        expected_version = request.expected_proposal_version_id
        expected_receipt = request.expected_proposal_receipt_ref
        if (expected_version is None) != (expected_receipt is None):
            raise HTTPException(
                status_code=422,
                detail="expected proposal version and receipt must be supplied together",
            )
        if expected_version is not None and expected_receipt is not None:
            require_current_proposal_version(
                proposal_id,
                expected_version_id=expected_version.strip(),
                expected_receipt_ref=expected_receipt.strip(),
                engine=engine,
                receipt_root=receipt_root,
            )
        result = create_governed_attestation(
            proposal_id=proposal_id,
            decision=request.decision,
            attester=request.attester.strip(),
            reason=request.reason.strip(),
            source_refs=list(request.source_refs),
            engine=engine,
            receipt_root=receipt_root,
        )
    except ProposalVersionResolutionError as exc:
        status = 404 if exc.code == "proposal_not_found" else 409
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc
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


@router.post("/proposals/{proposal_id}/review-events", response_model=ReviewEventCreateResponse)
async def add_review_event(
    proposal_id: str,
    request: ReviewEventCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write_capability: WriteCapabilityDependency,
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
        raise HTTPException(status_code=404, detail=f"proposal not found: {proposal_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ReviewEventCreateResponse(
        review_event=result.review_event,
        receipt_ref=result.receipt_ref,
        execution_allowed=False,
    )
