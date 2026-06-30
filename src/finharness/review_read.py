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
from typing import Any

from sqlalchemy import desc
from sqlmodel import Session, col, select

from finharness.annual_review import load_latest_annual_review
from finharness.rule_change_ledger import is_traceable, load_rule_changes
from finharness.statecore.models import Attestation, Proposal, ReviewEvent
from finharness.statecore.proposals import is_archived


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
    if event.kind != "agent_review_note" or not event.text:
        return detail
    try:
        payload = json.loads(event.text)
    except json.JSONDecodeError:
        detail.setdefault("data_gaps", []).append("agent review note payload is unreadable")
        return detail
    if isinstance(payload, dict):
        detail["agent_review_note"] = payload
    return detail


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
            session.exec(
                select(ReviewEvent).where(ReviewEvent.kind == "compare_mark")
            ).all()
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
            [f"compared proposal no longer exists (missing {missing_side})"]
            if missing_side
            else []
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
