"""Shared governed proposal writes for API and runtime loops."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.market_data import ROOT
from finharness.statecore.decision_scaffold import ensure_forcing
from finharness.statecore.models import (
    REVIEW_EVENT_KINDS,
    Attestation,
    Proposal,
    ReceiptIndex,
    ReviewEvent,
)
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.risk_classification import ensure_confirmable
from finharness.statecore.store import StateCoreStoreError, upsert_records, write_records

DecisionInput = Literal["approved", "rejected"]


@dataclass(frozen=True)
class GovernedProposalWrite:
    proposal: Proposal
    receipt_ref: str
    execution_allowed: bool = False


@dataclass(frozen=True)
class GovernedAttestationWrite:
    attestation: Attestation
    proposal: Proposal
    receipt_ref: str
    approved_is_not_execution_authorization: bool = True
    execution_allowed: bool = False


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _revision_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _safe_id(value: str) -> str:
    # Map every path-significant character (including ".") to "_", so an id can never
    # carry a ".." traversal segment even before resolve_under guards the final path.
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


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


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _content_hash(
    *,
    kind: str,
    claim: str,
    evidence: dict[str, Any],
    assumptions: dict[str, Any],
    limitations: dict[str, Any],
    non_claims: list[str],
    source_refs: list[str],
    decision_scaffold: dict[str, Any] | None = None,
) -> str:
    """Stable hash of a proposal's substantive content (excludes timestamps/ids).

    Two writes with identical content hash to the same value, so an idempotent
    re-scan that sees no change does not append a redundant receipt revision. The
    decision scaffold is substantive content, so a changed scaffold writes a new
    revision.
    """
    canonical = json.dumps(
        {
            "kind": kind,
            "claim": claim,
            "evidence": evidence,
            "assumptions": assumptions,
            "limitations": limitations,
            "non_claims": non_claims,
            "source_refs": source_refs,
            "decision_scaffold": decision_scaffold or {},
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _content_hash_of_row(proposal: Proposal) -> str:
    return _content_hash(
        kind=proposal.kind,
        claim=proposal.claim,
        evidence=proposal.evidence,
        assumptions=proposal.assumptions,
        limitations=proposal.limitations,
        non_claims=proposal.non_claims,
        source_refs=proposal.source_refs,
        decision_scaffold=proposal.decision_scaffold,
    )


def _proposal_receipt_payload(
    proposal: Proposal,
    receipt_id: str,
    *,
    content_hash: str,
    supersedes: str | None,
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "state_core_proposal",
        "created_at_utc": proposal.created_at_utc,
        "content_hash": content_hash,
        "supersedes": supersedes,
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


def create_governed_proposal(
    *,
    kind: str,
    claim: str,
    evidence: dict[str, Any],
    assumptions: dict[str, Any] | None = None,
    limitations: dict[str, Any] | None = None,
    non_claims: list[str] | None = None,
    source_refs: list[str] | None = None,
    decision_scaffold: dict[str, Any] | None = None,
    engine: Engine,
    receipt_root: str | Path,
    proposal_id: str | None = None,
    created_at_utc: str | None = None,
    idempotent: bool = False,
) -> GovernedProposalWrite:
    """Write a governed proposal without execution authority.

    The ``Proposal`` row is current-state (idempotent upsert by id). The receipt
    file is **append-only**: each content change writes a new revision
    (``receipt_<id>_<stamp>_<hash8>.json``), the receipt index keeps every
    revision, and the proposal points at the latest. An idempotent re-write whose
    content is unchanged is a no-op (no redundant revision), so the audit/replay
    chain records what changed and when, without noise.
    """
    created_at = created_at_utc or _now_utc()
    resolved_proposal_id = _safe_id(proposal_id or f"prop_{_stamp()}_{uuid4().hex[:8]}")
    final_non_claims = _dedupe_text(
        [
            *(non_claims or []),
            "Not execution authorization.",
            "Not investment advice.",
        ]
    )
    final_evidence = evidence
    final_assumptions = assumptions or {}
    final_limitations = limitations or {}
    final_source_refs = list(source_refs or [])
    # Forcing gate: a governed (needs_human_confirm) proposal must carry the four
    # required decision-scaffold fields. Fail-closed if any are missing/blank.
    final_scaffold = ensure_forcing(decision_scaffold)
    content_hash = _content_hash(
        kind=kind.strip(),
        claim=claim.strip(),
        evidence=final_evidence,
        assumptions=final_assumptions,
        limitations=final_limitations,
        non_claims=final_non_claims,
        source_refs=final_source_refs,
        decision_scaffold=final_scaffold,
    )

    supersedes: str | None = None
    if idempotent:
        with Session(engine) as session:
            existing = session.get(Proposal, resolved_proposal_id)
        if existing is not None:
            if _content_hash_of_row(existing) == content_hash:
                # Unchanged content: keep the existing latest revision, no new file.
                return GovernedProposalWrite(
                    proposal=existing,
                    receipt_ref=existing.receipt_ref or "",
                    execution_allowed=False,
                )
            supersedes = existing.receipt_ref

    receipt_id = f"receipt_{resolved_proposal_id}_{_revision_stamp()}_{content_hash[:8]}"
    receipt_path = resolve_under(receipt_root, "proposals", f"{receipt_id}.json")
    receipt_ref = _display_path(receipt_path)
    proposal = Proposal(
        proposal_id=resolved_proposal_id,
        kind=kind.strip(),
        claim=claim.strip(),
        evidence=final_evidence,
        assumptions=final_assumptions,
        limitations=final_limitations,
        non_claims=final_non_claims,
        source_refs=final_source_refs,
        decision_scaffold=final_scaffold,
        execution_allowed=False,
        receipt_ref=receipt_ref,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    receipt_payload = _proposal_receipt_payload(
        proposal, receipt_id, content_hash=content_hash, supersedes=supersedes
    )
    receipt_existed = receipt_path.exists()
    atomic_write_json(receipt_path, receipt_payload)
    receipt_index = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_proposal",
        path=receipt_path,
        created_at_utc=created_at,
        refs=[resolved_proposal_id, *final_source_refs],
    )
    try:
        # Proposal row is upserted to latest; the receipt revision is always a new
        # (unique) row, so revision history accumulates append-only.
        if idempotent:
            upsert_records([proposal, receipt_index], engine=engine)
        else:
            write_records([proposal, receipt_index], engine=engine)
    except StateCoreStoreError:
        if not receipt_existed:
            remove_file_best_effort(receipt_path)
        raise
    return GovernedProposalWrite(
        proposal=proposal,
        receipt_ref=receipt_ref,
        execution_allowed=False,
    )


def create_governed_attestation(
    *,
    proposal_id: str,
    decision: DecisionInput,
    attester: str,
    reason: str,
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> GovernedAttestationWrite:
    """Write a human attestation; approval remains non-execution authorization."""
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
    if proposal is None:
        raise KeyError(proposal_id)

    # P5 forcing gate (approval-time): a high-risk proposal may be recorded and
    # reviewed, but it cannot be *approved* without counter-evidence. Fail-closed
    # before any write so no half-written attestation row/receipt can exist.
    if decision == "approved":
        ensure_confirmable(
            kind=proposal.kind,
            evidence=proposal.evidence,
            decision_scaffold=proposal.decision_scaffold,
        )

    created_at = _now_utc()
    attestation_id = _safe_id(f"att_{_stamp()}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{attestation_id}"
    receipt_path = resolve_under(receipt_root, "attestations", f"{receipt_id}.json")
    receipt_ref = _display_path(receipt_path)
    attestation = Attestation(
        attestation_id=attestation_id,
        proposal_id=proposal.proposal_id,
        attester=attester.strip(),
        reason=reason.strip(),
        decision=decision,
        source_refs=[
            ref
            for ref in [proposal.receipt_ref, receipt_ref, *(source_refs or [])]
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
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return GovernedAttestationWrite(
        attestation=attestation,
        proposal=proposal,
        receipt_ref=receipt_ref,
        approved_is_not_execution_authorization=True,
        execution_allowed=False,
    )


ReviewEventKind = Literal["annotation", "archive", "reopen", "compare_mark"]


@dataclass(frozen=True)
class GovernedReviewEventWrite:
    review_event: ReviewEvent
    receipt_ref: str
    execution_allowed: bool = False


def _review_event_content_hash(
    *,
    proposal_id: str,
    kind: str,
    attester: str,
    reason: str,
    text: str | None,
    attestation_ref: str | None,
    compare_with: str | None,
    source_refs: list[str],
    created_at_utc: str,
) -> str:
    core = {
        "proposal_id": proposal_id,
        "kind": kind,
        "attester": attester,
        "reason": reason,
        "text": text,
        "attestation_ref": attestation_ref,
        "compare_with": compare_with,
        "source_refs": source_refs,
        "created_at_utc": created_at_utc,
    }
    return hashlib.sha256(
        json.dumps(core, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _review_event_receipt_payload(event: ReviewEvent, proposal: Proposal) -> dict[str, Any]:
    return {
        "receipt_id": f"receipt_{event.review_event_id}",
        "kind": "state_core_review_event",
        "created_at_utc": event.created_at_utc,
        "proposal_id": proposal.proposal_id,
        "proposal_receipt_ref": proposal.receipt_ref,
        "review_event": event.model_dump(mode="json"),
        "governance": {
            "execution_allowed": False,
            "not_execution_authorization": True,
            "not_investment_advice": True,
        },
    }


def create_governed_review_event(
    *,
    proposal_id: str,
    kind: ReviewEventKind,
    attester: str,
    reason: str,
    text: str | None = None,
    attestation_ref: str | None = None,
    compare_with: str | None = None,
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> GovernedReviewEventWrite:
    """Append a human review event (annotation/archive/reopen/compare_mark).

    Receipt-backed and append-only: a unique id is minted, the receipt is written, then
    the DB record; on DB failure the freshly written receipt is cleaned up. content_hash
    is integrity/replay only (not idempotency) — a repeated annotation is a new event.
    """
    # Enforce inputs here: SQLModel table models do not run field validators on
    # construction, so the create function is the real input guard (the DB CheckConstraint
    # guards execution_allowed at persistence).
    if kind not in REVIEW_EVENT_KINDS:
        raise ValueError(f"unknown review event kind: {kind}")
    if not attester.strip() or not reason.strip():
        raise ValueError("review event requires a named human and written reason")
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
    if proposal is None:
        raise KeyError(proposal_id)

    if kind == "compare_mark":
        target = (compare_with or "").strip()
        if not target:
            raise ValueError("compare_mark requires a compare_with proposal id")
        if target == proposal.proposal_id:
            raise ValueError("compare_mark cannot compare a proposal with itself")
        with Session(engine) as session:
            if session.get(Proposal, target) is None:
                raise KeyError(target)
        compare_with = target

    created_at = _now_utc()
    review_event_id = _safe_id(f"rev_{kind}_{_revision_stamp()}_{uuid4().hex[:8]}")
    content_hash = _review_event_content_hash(
        proposal_id=proposal.proposal_id,
        kind=kind,
        attester=attester.strip(),
        reason=reason.strip(),
        text=text,
        attestation_ref=attestation_ref,
        compare_with=compare_with,
        source_refs=list(source_refs or []),
        created_at_utc=created_at,
    )
    receipt_id = f"receipt_{review_event_id}"
    receipt_path = resolve_under(receipt_root, "review-events", f"{receipt_id}.json")
    receipt_ref = _display_path(receipt_path)
    event = ReviewEvent(
        review_event_id=review_event_id,
        proposal_id=proposal.proposal_id,
        kind=kind,
        attester=attester.strip(),
        reason=reason.strip(),
        text=text,
        attestation_ref=attestation_ref,
        compare_with=compare_with,
        source_refs=[
            ref
            for ref in [proposal.receipt_ref, receipt_ref, *(source_refs or [])]
            if ref
        ],
        content_hash=content_hash,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(receipt_path, _review_event_receipt_payload(event, proposal))
    receipt_index = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_review_event",
        path=receipt_path,
        created_at_utc=created_at,
        refs=[ref for ref in [proposal.receipt_ref, proposal.proposal_id] if ref],
    )
    try:
        write_records([event, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return GovernedReviewEventWrite(review_event=event, receipt_ref=receipt_ref)


def _latest_archive_event(events: list[ReviewEvent]) -> ReviewEvent | None:
    # Stable ordering: created_at_utc then review_event_id, so same-second events resolve
    # deterministically. Only archive/reopen toggle the derived state.
    toggles = [event for event in events if event.kind in ("archive", "reopen")]
    if not toggles:
        return None
    toggles.sort(key=lambda event: (event.created_at_utc, event.review_event_id))
    return toggles[-1]


def is_archived(proposal_id: str, *, engine: Engine) -> bool:
    """Derive archived state from the latest archive/reopen event (append-only history)."""
    with Session(engine) as session:
        events = list(
            session.exec(
                select(ReviewEvent).where(ReviewEvent.proposal_id == proposal_id)
            )
        )
    latest = _latest_archive_event(events)
    return latest is not None and latest.kind == "archive"


def archived_proposal_ids(engine: Engine) -> set[str]:
    """Set of proposal ids whose latest archive/reopen toggle is 'archive'."""
    with Session(engine) as session:
        events = list(session.exec(select(ReviewEvent)))
    by_proposal: dict[str, list[ReviewEvent]] = {}
    for event in events:
        by_proposal.setdefault(event.proposal_id, []).append(event)
    return {
        proposal_id
        for proposal_id, proposal_events in by_proposal.items()
        if (latest := _latest_archive_event(proposal_events)) is not None
        and latest.kind == "archive"
    }
