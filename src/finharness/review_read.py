"""Review System read models (S4 R4a-0).

The single place that turns Review-System state (proposals, attestations, review events,
annual-review receipts, rule-change ledger) into read-only DTOs for the API/cockpit
adapters. Pure reads: no writes, no execution. Lives above ``statecore`` (it composes
``statecore`` + ``annual_review`` + ``rule_change_ledger``) to avoid an import cycle.

R4a-0 consolidates the timeline and retrospective read logic (previously inline in the
route handlers); behavior is unchanged (snapshot-locked by the existing route tests).
R4a adds the compare-marks read model here as the system's natural extension.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import desc
from sqlmodel import Session, col, select

from finharness.annual_review import load_latest_annual_review
from finharness.project_paths import ROOT
from finharness.proposal_queue_checks import build_proposal_queue_checks
from finharness.rule_change_ledger import is_traceable, load_rule_changes
from finharness.statecore.models import (
    Attestation,
    Proposal,
    ReceiptIndex,
    ReviewEvent,
    attestation_closes_current_review,
)
from finharness.statecore.proposal_revisions import walk_proposal_revisions
from finharness.statecore.proposals import is_archived

ReviewQueueStatus = Literal[
    "needs_human_review",
    "blocked_for_missing_evidence",
    "reviewed",
    "archived",
]
ReviewQueuePriority = Literal["high", "medium", "low"]
ReviewQueueEvidenceStatus = Literal[
    "complete",
    "incomplete",
    "needs_context",
    "needs_counter_evidence",
]

REVIEW_QUEUE_NON_CLAIMS: tuple[str, ...] = (
    "Review queue triage is a derived read model, not approval.",
    "Queue priority does not rank investment merit or authorize execution.",
    "Review queue items are not attestation, rejection, or investment advice.",
)


@dataclass(frozen=True)
class TimelineEntry:
    source_type: str  # "attestation" | "review_event"
    id: str
    kind: str
    created_at_utc: str
    attester: str
    reason: str
    detail: dict[str, Any]


@dataclass(frozen=True)
class ProposalTimeline:
    proposal_id: str
    is_archived: bool
    entries: list[TimelineEntry]


@dataclass(frozen=True)
class RuleChangeRow:
    rule_change_id: str
    rule_target: str
    change_kind: str
    status: str
    attester: str
    traceable: bool


@dataclass(frozen=True)
class Retrospective:
    retrospective: dict[str, Any] | None
    retrospective_receipt_ref: str | None
    rule_changes: list[RuleChangeRow]
    data_gaps: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ComparePair:
    proposal_id: str
    compare_with: str
    attester: str
    reason: str
    created_at_utc: str
    review_event_id: str
    proposal_exists: bool
    compare_with_exists: bool
    missing_side: str | None  # "left" | "right" | "both" | None
    data_gaps: list[str]


@dataclass(frozen=True)
class ReviewQueueItem:
    proposal_id: str
    kind: str
    claim: str
    created_at_utc: str
    receipt_ref: str | None
    status: ReviewQueueStatus
    priority: ReviewQueuePriority
    triage_reasons: list[str]
    evidence_status: ReviewQueueEvidenceStatus
    review_note_count: int
    latest_review_note_summary: str | None
    open_questions: list[str]
    risks: list[str]
    data_gaps: list[str]
    duplicate_candidates: list[str]
    stale_context_flags: list[str]
    source_refs: list[str]
    receipt_refs: list[str]
    next_actions: list[str]
    execution_allowed: bool = False
    authority_transition: bool = False


@dataclass(frozen=True)
class ReviewQueue:
    items: list[ReviewQueueItem]
    non_claims: tuple[str, ...] = REVIEW_QUEUE_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


def read_proposal_timeline(engine: Any, proposal_id: str) -> ProposalTimeline | None:
    """Merged review timeline (attestations + review events), newest-first.

    Returns ``None`` when the proposal does not exist (the adapter maps that to 404).
    Order: ``(created_at_utc, source_type, id)`` all descending — deterministic, no jitter.
    """
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        if proposal is None:
            return None
        attestations = list(
            session.exec(
                select(Attestation)
                .where(Attestation.proposal_id == proposal_id)
                .order_by(desc(Attestation.created_at_utc), desc(Attestation.attestation_id))
            ).all()
        )
        events = list(
            session.exec(select(ReviewEvent).where(ReviewEvent.proposal_id == proposal_id)).all()
        )
    entries = [
        TimelineEntry(
            source_type="attestation",
            id=att.attestation_id,
            kind=att.decision,
            created_at_utc=att.created_at_utc,
            attester=att.attester,
            reason=att.reason,
            detail=att.model_dump(mode="json"),
        )
        for att in attestations
    ] + [
        TimelineEntry(
            source_type="review_event",
            id=event.review_event_id,
            kind=event.kind,
            created_at_utc=event.created_at_utc,
            attester=event.attester,
            reason=event.reason,
            detail=_review_event_detail(event),
        )
        for event in events
    ]
    entries.sort(
        key=lambda entry: (entry.created_at_utc, entry.source_type, entry.id), reverse=True
    )
    return ProposalTimeline(
        proposal_id=proposal_id,
        is_archived=is_archived(proposal_id, engine=engine),
        entries=entries,
    )


def _review_event_detail(event: ReviewEvent) -> dict[str, Any]:
    detail = event.model_dump(mode="json")
    artifact_keys = {
        "agent_review_note": "agent_review_note",
        "agent_scaffold_revision_apply_candidate": ("agent_scaffold_revision_apply_candidate"),
    }
    artifact_key = artifact_keys.get(event.kind)
    if artifact_key is None or not event.text:
        return detail
    try:
        payload = json.loads(event.text)
    except json.JSONDecodeError:
        label = event.kind.replace("_", " ")
        detail.setdefault("data_gaps", []).append(f"{label} payload is unreadable")
        return detail
    if isinstance(payload, dict):
        detail[artifact_key] = payload
    return detail


def _text_items(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _agent_proposal_context(
    proposal: Proposal,
    *,
    receipt_root: Path,
) -> dict[str, Any] | None:
    if not proposal.receipt_ref:
        return None
    walk = walk_proposal_revisions(
        proposal.proposal_id,
        proposal.receipt_ref,
        allowed_roots=(ROOT.resolve(), receipt_root),
        max_revisions=100,
    )
    for record in walk.revisions:
        context = record.revision_context
        if context.get("kind") == "agent_proposal_draft":
            return context
    return None


def _review_note_payloads(events: list[ReviewEvent]) -> list[dict[str, Any]]:
    return [payload for _, payload in _review_note_payload_pairs(events)]


def _review_note_payload_pairs(
    events: list[ReviewEvent],
) -> list[tuple[ReviewEvent, dict[str, Any]]]:
    pairs: list[tuple[ReviewEvent, dict[str, Any]]] = []
    for event in events:
        if event.kind != "agent_review_note" or not event.text:
            continue
        try:
            payload = json.loads(event.text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            pairs.append((event, payload))
    return pairs


def _unreadable_review_note_gaps(events: list[ReviewEvent]) -> list[str]:
    gaps: list[str] = []
    for event in events:
        if event.kind != "agent_review_note" or not event.text:
            continue
        try:
            payload = json.loads(event.text)
        except json.JSONDecodeError:
            gaps.append("agent review note payload is unreadable")
            continue
        if not isinstance(payload, dict):
            gaps.append("agent review note payload is not an object")
    return gaps


def _source_refs_for(queue_source_refs: list[str], notes: list[dict[str, Any]]) -> list[str]:
    refs = list(queue_source_refs)
    for note in notes:
        refs.extend(_text_items(note.get("source_refs")))
        refs.extend(_text_items(note.get("evidence_refs")))
    return sorted(set(refs))


def _receipt_refs_for(proposal: Proposal, events: list[ReviewEvent]) -> list[str]:
    refs: list[str] = []
    if proposal.receipt_ref:
        refs.append(proposal.receipt_ref)
    for note in _review_note_payloads(events):
        refs.extend(_text_items(note.get("receipt_refs")))
        receipt_ref = note.get("receipt_ref")
        if isinstance(receipt_ref, str) and receipt_ref.strip():
            refs.append(receipt_ref.strip())
    return sorted(set(refs))


def _queue_status(
    *,
    proposal_id: str,
    archived_ids: set[str],
    attested_ids: set[str],
    evidence_status: ReviewQueueEvidenceStatus,
) -> ReviewQueueStatus:
    if proposal_id in archived_ids:
        return "archived"
    if proposal_id in attested_ids:
        return "reviewed"
    if evidence_status != "complete":
        return "blocked_for_missing_evidence"
    return "needs_human_review"


def _queue_priority(
    *,
    status: ReviewQueueStatus,
    block_codes: set[str],
    note_severities: list[str],
    has_open_questions: bool,
) -> ReviewQueuePriority:
    if status in {"archived", "reviewed"}:
        return "low"
    if block_codes or any(severity in {"high", "blocking"} for severity in note_severities):
        return "high"
    if has_open_questions:
        return "high"
    return "medium"


def _evidence_status(
    *,
    block_codes: set[str],
    data_gaps: list[str],
    stale_context_flags: list[str],
    receipt_ref_missing: bool,
) -> ReviewQueueEvidenceStatus:
    if "counter_evidence_needed" in block_codes:
        return "needs_counter_evidence"
    if stale_context_flags or "stale_context" in block_codes:
        return "needs_context"
    if (
        receipt_ref_missing
        or data_gaps
        or block_codes & {"missing_source_refs", "data_gap", "policy_mismatch"}
    ):
        return "incomplete"
    return "complete"


def _next_actions(
    *,
    status: ReviewQueueStatus,
    block_codes: set[str],
    has_open_questions: bool,
    duplicate_candidates: list[str],
    stale_context_flags: list[str],
) -> list[str]:
    actions: list[str] = []
    if status == "archived":
        return ["no active review action unless a human reopens the proposal"]
    if status == "reviewed":
        return ["inspect historical review evidence if needed"]
    if "missing_source_refs" in block_codes:
        actions.append("attach source references before human attestation")
    if "counter_evidence_needed" in block_codes:
        actions.append("add counter-evidence to the decision scaffold")
    if "data_gap" in block_codes:
        actions.append("resolve recorded data gaps or document why review can continue")
    if "policy_mismatch" in block_codes:
        actions.append("resolve policy mismatch or keep human review blocked")
    if stale_context_flags or "stale_context" in block_codes:
        actions.append("refresh stale context or attach current receipt/source refs")
    if duplicate_candidates:
        actions.append("compare duplicate candidates before progressing review")
    if has_open_questions:
        actions.append("answer Agent open questions")
    if not actions:
        actions.append("review proposal and record attestation or review event")
    return actions


def _build_review_queue_item(
    proposal: Proposal,
    *,
    events: list[ReviewEvent],
    archived_ids: set[str],
    attested_ids: set[str],
    indexed_receipt_refs: set[str],
    receipt_root: Path,
    engine: Any,
) -> ReviewQueueItem:
    agent_context = _agent_proposal_context(proposal, receipt_root=receipt_root)
    open_for_review = proposal.proposal_id not in attested_ids
    queue_checks = build_proposal_queue_checks(
        proposal,
        engine=engine,
        open_for_review=open_for_review,
        created_by="agent" if agent_context else "human_or_system",
        active_profile=str(agent_context.get("profile")) if agent_context else None,
        source_refs=list(proposal.source_refs),
        receipt_refs=[proposal.receipt_ref] if proposal.receipt_ref else [],
        context_pack_refs=_text_items(agent_context.get("context_pack_refs"))
        if agent_context
        else [],
    )
    note_pairs = _review_note_payload_pairs(events)
    notes = [payload for _, payload in note_pairs]
    open_questions = [item for note in notes for item in _text_items(note.get("open_questions"))]
    risks = [item for note in notes for item in _text_items(note.get("risks"))]
    note_data_gaps = [item for note in notes for item in _text_items(note.get("data_gaps"))]
    unreadable_note_gaps = _unreadable_review_note_gaps(events)
    duplicate_candidates = sorted(
        {
            proposal_id
            for finding in queue_checks.blocks
            if finding.code == "duplicate_proposal"
            for proposal_id in finding.related_proposal_ids
        }
    )
    stale_context_flags = [
        finding.message for finding in queue_checks.blocks if finding.code == "stale_context"
    ]
    for event, note in note_pairs:
        if note.get("proposal_id") != event.proposal_id:
            stale_context_flags.append("agent review note proposal_id does not match event")
        if not _text_items(note.get("context_pack_refs")):
            stale_context_flags.append("agent review note has no context_pack_refs")
    receipt_ref_missing = (
        not proposal.receipt_ref or proposal.receipt_ref not in indexed_receipt_refs
    )
    if receipt_ref_missing:
        stale_context_flags.append("proposal receipt_ref missing from receipt index")

    block_codes: set[str] = {str(finding.code) for finding in queue_checks.blocks}
    data_gaps = sorted({*note_data_gaps, *unreadable_note_gaps})
    evidence_status = _evidence_status(
        block_codes=block_codes,
        data_gaps=data_gaps,
        stale_context_flags=stale_context_flags,
        receipt_ref_missing=receipt_ref_missing,
    )
    status = _queue_status(
        proposal_id=proposal.proposal_id,
        archived_ids=archived_ids,
        attested_ids=attested_ids,
        evidence_status=evidence_status,
    )
    note_severities = [str(note.get("suggested_severity") or "").strip().lower() for note in notes]
    priority = _queue_priority(
        status=status,
        block_codes=block_codes - {"human_review_required"},
        note_severities=note_severities,
        has_open_questions=bool(open_questions),
    )
    triage_reasons = [finding.message for finding in queue_checks.blocks]
    if open_questions:
        triage_reasons.append("Agent review note reports open questions.")
    if risks:
        triage_reasons.append("Agent review note reports review risks.")
    if data_gaps:
        triage_reasons.append("Agent review note reports data gaps.")
    latest_note = notes[0] if notes else None
    return ReviewQueueItem(
        proposal_id=proposal.proposal_id,
        kind=proposal.kind,
        claim=proposal.claim,
        created_at_utc=proposal.created_at_utc,
        receipt_ref=proposal.receipt_ref,
        status=status,
        priority=priority,
        triage_reasons=triage_reasons,
        evidence_status=evidence_status,
        review_note_count=len(notes),
        latest_review_note_summary=(
            str(latest_note.get("summary")).strip()
            if latest_note and latest_note.get("summary")
            else None
        ),
        open_questions=sorted(set(open_questions)),
        risks=sorted(set(risks)),
        data_gaps=data_gaps,
        duplicate_candidates=duplicate_candidates,
        stale_context_flags=sorted(set(stale_context_flags)),
        source_refs=_source_refs_for(list(queue_checks.source_refs), notes),
        receipt_refs=_receipt_refs_for(proposal, events),
        next_actions=_next_actions(
            status=status,
            block_codes=block_codes,
            has_open_questions=bool(open_questions),
            duplicate_candidates=duplicate_candidates,
            stale_context_flags=stale_context_flags,
        ),
        execution_allowed=False,
        authority_transition=False,
    )


def read_review_queue(
    engine: Any,
    *,
    receipt_root: Path,
    limit: int = 50,
    include_closed: bool = False,
) -> ReviewQueue:
    """Derived, deterministic review queue triage.

    This read model composes proposals, attestations, review events, receipt
    index rows, and existing proposal queue checks. It never writes, never calls
    models/providers, and never grants approval or execution authority.
    """
    with Session(engine) as session:
        proposals = list(
            session.exec(
                select(Proposal).order_by(desc(Proposal.created_at_utc), desc(Proposal.proposal_id))
            ).all()
        )
        attestations = list(session.exec(select(Attestation)).all())
        events = list(session.exec(select(ReviewEvent)).all())
        receipt_index = list(session.exec(select(ReceiptIndex)).all())

    archived_ids = {
        proposal.proposal_id
        for proposal in proposals
        if is_archived(proposal.proposal_id, engine=engine)
    }
    proposals_by_id = {proposal.proposal_id: proposal for proposal in proposals}
    attested_ids = {
        attestation.proposal_id
        for attestation in attestations
        if (proposal := proposals_by_id.get(attestation.proposal_id)) is not None
        and attestation_closes_current_review(attestation, proposal)
    }
    events_by_proposal: dict[str, list[ReviewEvent]] = {}
    for event in events:
        events_by_proposal.setdefault(event.proposal_id, []).append(event)
    indexed_receipt_refs = {row.path for row in receipt_index}

    items = [
        _build_review_queue_item(
            proposal,
            events=sorted(
                events_by_proposal.get(proposal.proposal_id, []),
                key=lambda event: (event.created_at_utc, event.review_event_id),
                reverse=True,
            ),
            archived_ids=archived_ids,
            attested_ids=attested_ids,
            indexed_receipt_refs=indexed_receipt_refs,
            receipt_root=receipt_root,
            engine=engine,
        )
        for proposal in proposals
    ]
    if not include_closed:
        items = [item for item in items if item.status not in {"archived", "reviewed"}]
    priority_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(
        key=lambda item: (
            priority_order[item.priority],
            item.created_at_utc,
            item.proposal_id,
        ),
        reverse=False,
    )
    return ReviewQueue(items=items[:limit])


def read_retrospective(
    annual_review_root: str | Path, rule_change_state_root: str | Path
) -> Retrospective:
    """Latest annual_review receipt (field pass-through, never recomputed) + rule-change
    ledger drill-down + disclosed gaps. Pure read."""
    retrospective, receipt_ref, data_gaps = load_latest_annual_review(annual_review_root)
    rule_changes: list[RuleChangeRow] = []
    try:
        for change in load_rule_changes(Path(rule_change_state_root)):
            rule_changes.append(
                RuleChangeRow(
                    rule_change_id=change.rule_change_id,
                    rule_target=change.rule_target,
                    change_kind=change.change_kind,
                    status=change.status,
                    attester=change.attester,
                    traceable=is_traceable(change),
                )
            )
    except Exception as exc:  # provenance is best-effort; never break the read
        data_gaps = [*data_gaps, f"rule-change ledger unreadable: {type(exc).__name__}"]
    return Retrospective(
        retrospective=retrospective,
        retrospective_receipt_ref=receipt_ref,
        rule_changes=rule_changes,
        data_gaps=data_gaps,
    )


def read_compare_marks(engine: Any) -> list[ComparePair]:
    """Compare-marked proposal pairs (canonical unordered {A,B}, latest event wins).

    A->B and B->A are the same pair; repeated marks collapse to the most recent event by
    ``(created_at_utc, review_event_id)``, whose direction/attester/reason are shown. A
    side whose proposal no longer exists is flagged (``missing_side`` + ``data_gaps``), not
    crashed. Pure read; never writes. List is newest-first by the winning event.
    """
    with Session(engine) as session:
        events = list(
            session.exec(select(ReviewEvent).where(ReviewEvent.kind == "compare_mark")).all()
        )
        latest: dict[frozenset[str], ReviewEvent] = {}
        for event in events:
            if not event.compare_with:
                continue  # defensive: compare_mark is validated to carry a target
            key = frozenset({event.proposal_id, event.compare_with})
            current = latest.get(key)
            if current is None or (event.created_at_utc, event.review_event_id) > (
                current.created_at_utc,
                current.review_event_id,
            ):
                latest[key] = event
        ids = {pid for event in latest.values() for pid in (event.proposal_id, event.compare_with)}
        existing: set[str] = set()
        if ids:
            existing = {
                proposal.proposal_id
                for proposal in session.exec(
                    select(Proposal).where(col(Proposal.proposal_id).in_(ids))
                ).all()
            }
    pairs: list[ComparePair] = []
    for event in latest.values():
        left_ok = event.proposal_id in existing
        right_ok = (event.compare_with or "") in existing
        if not left_ok and not right_ok:
            missing_side: str | None = "both"
        elif not left_ok:
            missing_side = "left"
        elif not right_ok:
            missing_side = "right"
        else:
            missing_side = None
        gaps = (
            [f"compared proposal no longer exists (missing {missing_side})"] if missing_side else []
        )
        pairs.append(
            ComparePair(
                proposal_id=event.proposal_id,
                compare_with=event.compare_with or "",
                attester=event.attester,
                reason=event.reason,
                created_at_utc=event.created_at_utc,
                review_event_id=event.review_event_id,
                proposal_exists=left_ok,
                compare_with_exists=right_ok,
                missing_side=missing_side,
                data_gaps=gaps,
            )
        )
    pairs.sort(key=lambda pair: (pair.created_at_utc, pair.review_event_id), reverse=True)
    return pairs
