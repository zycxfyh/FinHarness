"""Read-only proposal queue checks for Agent-created review drafts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from finharness.statecore.models import (
    Attestation,
    Proposal,
    attestation_closes_current_review,
)
from finharness.statecore.proposals import archived_proposal_ids
from finharness.statecore.risk_classification import is_high_risk

QueueCheckCode = Literal[
    "missing_source_refs",
    "counter_evidence_needed",
    "data_gap",
    "duplicate_proposal",
    "stale_context",
    "policy_mismatch",
    "human_review_required",
]
QueueCheckSeverity = Literal["warn", "block"]
QueueCheckState = Literal["pass", "warn", "block"]
QueueCheckBlockedTransition = Literal[
    "review_entry",
    "human_attestation",
    "authority_transition",
    "execution",
]
QueueCheckClassification = Literal[
    "authority_boundary",
    "duplicate",
    "evidence_gap",
    "policy",
    "readiness",
]
QueueCheckCreatedBy = Literal["agent", "human_or_system"]


class QueueCheckFinding(BaseModel):
    """Machine-readable finding for proposal review queue readiness."""

    code: QueueCheckCode
    severity: QueueCheckSeverity
    classification: QueueCheckClassification
    message: str
    recovery_hint: str
    blocked_transitions: tuple[QueueCheckBlockedTransition, ...] = ()
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    related_proposal_ids: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    execution_allowed: bool = False
    authority_transition: bool = False


class ProposalQueueChecks(BaseModel):
    """Read-only queue check summary for a proposal."""

    proposal_id: str
    created_by: QueueCheckCreatedBy
    active_profile: str | None = None
    check_state: QueueCheckState
    blocks: list[QueueCheckFinding] = Field(default_factory=list)
    warnings: list[QueueCheckFinding] = Field(default_factory=list)
    blocked_transitions: tuple[QueueCheckBlockedTransition, ...] = ()
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    context_pack_refs: list[str] = Field(default_factory=list)
    open_for_review: bool
    requires_human_review: bool = True
    execution_allowed: bool = False
    authority_transition: bool = False
    evaluated_kinds: tuple[QueueCheckCode, ...] = (
        "missing_source_refs",
        "counter_evidence_needed",
        "data_gap",
        "duplicate_proposal",
        "stale_context",
        "policy_mismatch",
        "human_review_required",
    )
    non_claims: tuple[str, ...] = (
        "Proposal queue checks are review readiness metadata, not approval.",
        "Queue pass/warn/block does not authorize execution.",
        "A block names the transition it blocks; human review required does "
        "not block review entry.",
        "Human attestation remains outside Agent authority.",
    )


def _text_list(values: list[str] | tuple[str, ...] | None) -> list[str]:
    if values is None:
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _truthy_marker(mapping: dict[str, Any], keys: tuple[str, ...]) -> bool:
    for key in keys:
        value = mapping.get(key)
        if value in (None, False, "", [], {}):
            continue
        return True
    return False


def _blank(value: object) -> bool:
    return not str(value or "").strip()


def _norm(value: str) -> str:
    return " ".join(value.strip().lower().split())


def _duplicate_open_proposal_ids(proposal: Proposal, *, engine: Engine) -> list[str]:
    archived = archived_proposal_ids(engine)
    with Session(engine) as session:
        proposals = list(session.exec(select(Proposal)).all())
        attestations = list(session.exec(select(Attestation)).all())

    proposals_by_id = {candidate.proposal_id: candidate for candidate in proposals}
    attested_ids = {
        attestation.proposal_id
        for attestation in attestations
        if (bound := proposals_by_id.get(attestation.proposal_id)) is not None
        and attestation_closes_current_review(attestation, bound)
    }
    kind = _norm(proposal.kind)
    claim = _norm(proposal.claim)
    duplicates: list[str] = []
    for candidate in proposals:
        if candidate.proposal_id == proposal.proposal_id:
            continue
        if candidate.proposal_id in archived or candidate.proposal_id in attested_ids:
            continue
        if _norm(candidate.kind) == kind and _norm(candidate.claim) == claim:
            duplicates.append(candidate.proposal_id)
    return sorted(duplicates)


def _blocked_transition_summary(
    blocks: list[QueueCheckFinding],
) -> tuple[QueueCheckBlockedTransition, ...]:
    order: tuple[QueueCheckBlockedTransition, ...] = (
        "review_entry",
        "human_attestation",
        "authority_transition",
        "execution",
    )
    present = {transition for finding in blocks for transition in finding.blocked_transitions}
    return tuple(transition for transition in order if transition in present)


def build_proposal_queue_checks(
    proposal: Proposal,
    *,
    engine: Engine,
    open_for_review: bool,
    created_by: QueueCheckCreatedBy = "human_or_system",
    active_profile: str | None = None,
    source_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
    context_pack_refs: list[str] | None = None,
) -> ProposalQueueChecks:
    """Build a read-only queue check response for a proposal.

    The checks are intentionally deterministic and local. They do not call
    models, providers, or external services, and they never change proposal
    state.
    """

    resolved_source_refs = _text_list(source_refs or proposal.source_refs)
    resolved_receipt_refs = _text_list(
        receipt_refs or ([proposal.receipt_ref] if proposal.receipt_ref else [])
    )
    resolved_context_pack_refs = _text_list(context_pack_refs)
    blocks: list[QueueCheckFinding] = []
    warnings: list[QueueCheckFinding] = []

    def block(
        code: QueueCheckCode,
        classification: QueueCheckClassification,
        message: str,
        recovery_hint: str,
        *,
        blocked_transitions: tuple[QueueCheckBlockedTransition, ...],
        source_refs_for_finding: list[str] | None = None,
        receipt_refs_for_finding: list[str] | None = None,
        related_proposal_ids: list[str] | None = None,
    ) -> None:
        blocks.append(
            QueueCheckFinding(
                code=code,
                severity="block",
                classification=classification,
                message=message,
                recovery_hint=recovery_hint,
                blocked_transitions=blocked_transitions,
                source_refs=source_refs_for_finding or [],
                receipt_refs=receipt_refs_for_finding or [],
                related_proposal_ids=related_proposal_ids or [],
                requires_human_review=True,
                execution_allowed=False,
                authority_transition=False,
            )
        )

    if not resolved_source_refs:
        block(
            "missing_source_refs",
            "evidence_gap",
            "Proposal has no source references attached to the review record.",
            "Attach source references or regenerate the draft from bounded context.",
            blocked_transitions=(
                "review_entry",
                "human_attestation",
                "authority_transition",
                "execution",
            ),
        )

    scaffold = proposal.decision_scaffold or {}
    if is_high_risk(proposal.kind, proposal.evidence) and _blank(scaffold.get("counter_evidence")):
        block(
            "counter_evidence_needed",
            "readiness",
            "Proposal decision scaffold lacks counter-evidence.",
            "Add a counter-evidence condition before human attestation.",
            blocked_transitions=(
                "human_attestation",
                "authority_transition",
                "execution",
            ),
        )

    if _truthy_marker(
        proposal.evidence,
        ("data_gap", "data_gaps", "missing_data"),
    ) or _truthy_marker(
        proposal.limitations,
        ("data_gap", "data_gaps", "missing_data"),
    ):
        block(
            "data_gap",
            "evidence_gap",
            "Proposal records an unresolved data gap.",
            "Resolve the data gap or record why review can proceed despite it.",
            blocked_transitions=(
                "human_attestation",
                "authority_transition",
                "execution",
            ),
            source_refs_for_finding=resolved_source_refs,
        )

    if _truthy_marker(proposal.evidence, ("stale_context", "source_stale")) or _truthy_marker(
        proposal.limitations,
        ("stale_context", "source_stale"),
    ):
        block(
            "stale_context",
            "evidence_gap",
            "Proposal marks its context or source evidence as stale.",
            "Refresh the context pack or attach a current receipt/source ref.",
            blocked_transitions=(
                "human_attestation",
                "authority_transition",
                "execution",
            ),
            source_refs_for_finding=resolved_source_refs,
            receipt_refs_for_finding=resolved_receipt_refs,
        )

    if _truthy_marker(proposal.evidence, ("policy_mismatch", "ips_mismatch")) or _truthy_marker(
        proposal.limitations,
        ("policy_mismatch", "ips_mismatch"),
    ):
        block(
            "policy_mismatch",
            "policy",
            "Proposal records a policy or IPS mismatch.",
            "Resolve the policy mismatch or keep the draft blocked for explicit human review.",
            blocked_transitions=(
                "human_attestation",
                "authority_transition",
                "execution",
            ),
            source_refs_for_finding=resolved_source_refs,
        )

    duplicates = _duplicate_open_proposal_ids(proposal, engine=engine)
    if duplicates:
        block(
            "duplicate_proposal",
            "duplicate",
            "Another open proposal has the same kind and claim.",
            "Review the existing open proposal before adding another draft to the queue.",
            blocked_transitions=(
                "review_entry",
                "authority_transition",
                "execution",
            ),
            related_proposal_ids=duplicates,
        )

    if created_by == "agent" and open_for_review:
        block(
            "human_review_required",
            "authority_boundary",
            "Agent-created proposal draft is pending human review.",
            "A human reviewer must attest or reject the proposal; this is not "
            "execution authorization.",
            blocked_transitions=(
                "human_attestation",
                "authority_transition",
                "execution",
            ),
            source_refs_for_finding=resolved_source_refs,
            receipt_refs_for_finding=resolved_receipt_refs,
        )

    check_state: QueueCheckState
    if blocks:
        check_state = "block"
    elif warnings:
        check_state = "warn"
    else:
        check_state = "pass"

    return ProposalQueueChecks(
        proposal_id=proposal.proposal_id,
        created_by=created_by,
        active_profile=active_profile,
        check_state=check_state,
        blocks=blocks,
        warnings=warnings,
        blocked_transitions=_blocked_transition_summary(blocks),
        source_refs=resolved_source_refs,
        receipt_refs=resolved_receipt_refs,
        context_pack_refs=resolved_context_pack_refs,
        open_for_review=open_for_review,
        requires_human_review=True,
        execution_allowed=False,
        authority_transition=False,
    )
