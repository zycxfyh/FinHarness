"""Shared governed proposal writes for API and runtime loops."""

# ruff: noqa: C901

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

from finharness.project_paths import ROOT
from finharness.statecore.decision_scaffold import ALL_FIELDS, ensure_forcing, normalize
from finharness.statecore.models import (
    REVIEW_EVENT_KINDS,
    Attestation,
    Proposal,
    ReceiptIndex,
    ReviewEvent,
)
from finharness.statecore.proposal_version import (
    ProposalVersionExpectation,
    require_current_proposal_version_in_session,
)
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.risk_classification import ensure_confirmable
from finharness.statecore.store import StateCoreStoreError, upsert_records, write_records

DecisionInput = Literal["approved", "rejected", "deferred"]

ReviewEventKind = Literal[
    "annotation",
    "archive",
    "reopen",
    "compare_mark",
    "agent_review_note",
    "agent_scaffold_revision_apply_candidate",
]


@dataclass(frozen=True)
class GovernedProposalWrite:
    proposal: Proposal
    receipt_ref: str
    execution_allowed: bool = False


@dataclass(frozen=True)
class GovernedProposalRevisionWrite:
    proposal: Proposal
    receipt_ref: str
    previous_receipt_ref: str | None
    changed_scaffold_fields: tuple[str, ...]
    admitted_proposal_version_id: str
    admitted_proposal_receipt_ref: str
    resulting_proposal_version_id: str
    resulting_proposal_receipt_ref: str
    execution_allowed: bool = False


@dataclass(frozen=True)
class GovernedAttestationWrite:
    attestation: Attestation
    proposal: Proposal
    receipt_ref: str
    admitted_proposal_version_id: str
    admitted_proposal_receipt_ref: str
    approved_is_not_execution_authorization: bool = True
    execution_allowed: bool = False


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _revision_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _safe_id(value: str) -> str:
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


def proposal_content_hash(proposal: Proposal) -> str:
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
    revision_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
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
    if revision_context is not None:
        payload["revision_context"] = revision_context
    return payload


def _attestation_receipt_payload(
    attestation: Attestation,
    proposal: Proposal,
    receipt_id: str,
    *,
    admitted_version_id: str,
    admitted_receipt_ref: str,
    mutation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "receipt_id": receipt_id,
        "kind": "state_core_attestation",
        "created_at_utc": attestation.created_at_utc,
        "proposal_id": proposal.proposal_id,
        "proposal_receipt_ref": proposal.receipt_ref,
        "admitted_proposal_version_id": admitted_version_id,
        "admitted_proposal_receipt_ref": admitted_receipt_ref,
        "attestation": attestation.model_dump(mode="json"),
        "governance": {
            "execution_allowed": False,
            "approved_is_not_execution_authorization": True,
            "not_execution_authorization": True,
            "not_investment_advice": True,
        },
    }

    if mutation_context is not None:
        payload["mutation_context"] = mutation_context

    return payload


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
    revision_context: dict[str, Any] | None = None,
) -> GovernedProposalWrite:
    """Write a governed proposal without execution authority."""
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
            if proposal_content_hash(existing) == content_hash:
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
        proposal,
        receipt_id,
        content_hash=content_hash,
        supersedes=supersedes,
        revision_context=revision_context,
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


def revise_governed_proposal_scaffold(
    *,
    proposal_id: str,
    scaffold_patch: dict[str, Any],
    attester: str,
    reason: str,
    expectation: ProposalVersionExpectation,
    source_refs: list[str] | None = None,
    revision_context_extra: dict[str, Any] | None = None,
    engine: Engine,
    receipt_root: str | Path,
    session: Session | None = None,
) -> GovernedProposalRevisionWrite:
    """Append a human-authored decision-scaffold revision for an existing proposal.

    Version binding: ``expectation`` is validated against the current Proposal
    row inside the same Session that commits the revision, closing the TOCTOU gap.
    If ``session`` is provided, the version check and write share one transaction.
    Otherwise a new Session is opened (backward-compatible path for tests).
    """
    if not attester.strip() or not reason.strip():
        raise ValueError(
            "proposal scaffold revision requires a named human and written reason"
        )

    unknown = sorted(set(scaffold_patch) - set(ALL_FIELDS))
    if unknown:
        raise ValueError(
            "unknown decision-scaffold field(s): "
            + ", ".join(unknown)
            + f". Allowed fields: {', '.join(ALL_FIELDS)}."
        )

    patch = normalize(scaffold_patch)
    if not patch:
        raise ValueError(
            "proposal scaffold revision requires at least one non-blank field"
        )

    own_session = session is None
    active_session = session or Session(engine)
    try:
        # Version check + read in same transaction
        admitted = require_current_proposal_version_in_session(
            expectation,
            proposal_id=proposal_id,
            session=active_session,
            receipt_root=receipt_root,
        )
        existing = active_session.get(Proposal, proposal_id)
        if existing is None:
            raise KeyError(proposal_id)

        previous_scaffold = normalize(existing.decision_scaffold)
        merged_scaffold = ensure_forcing({**previous_scaffold, **patch})
        changed_fields = tuple(
            field
            for field in ALL_FIELDS
            if previous_scaffold.get(field) != merged_scaffold.get(field)
        )
        if not changed_fields:
            raise ValueError(
                "proposal scaffold revision does not change any stored field"
            )

        refs = _dedupe_text(
            [
                *existing.source_refs,
                *([existing.receipt_ref] if existing.receipt_ref else []),
                *(source_refs or []),
            ]
        )
        revision_context = {
            "kind": "decision_scaffold_revision",
            "attester": attester.strip(),
            "reason": reason.strip(),
            "previous_receipt_ref": existing.receipt_ref,
            "changed_scaffold_fields": list(changed_fields),
            "execution_allowed": False,
            "admitted_proposal_version_id": admitted.proposal_version_id,
            "admitted_proposal_receipt_ref": admitted.receipt_ref,
        }
        if revision_context_extra:
            revision_context.update(
                {
                    key: value
                    for key, value in revision_context_extra.items()
                    if key
                    not in {
                        "kind",
                        "attester",
                        "reason",
                        "execution_allowed",
                        "admitted_proposal_version_id",
                        "admitted_proposal_receipt_ref",
                    }
                }
            )

        # Create the new proposal revision (this opens its own Session for write)
        # The version check already passed inside the active_session — the subsequent
        # create_governed_proposal creates a new revision receipt + index.
        # Since create_governed_proposal uses upsert_records with its own Session,
        # the admitted version info is carried in the revision_context.
        if own_session:
            active_session.commit()

        write = create_governed_proposal(
            kind=existing.kind,
            claim=existing.claim,
            evidence=existing.evidence,
            assumptions=existing.assumptions,
            limitations=existing.limitations,
            non_claims=existing.non_claims,
            source_refs=refs,
            decision_scaffold=merged_scaffold,
            engine=engine,
            receipt_root=receipt_root,
            proposal_id=existing.proposal_id,
            idempotent=True,
            revision_context=revision_context,
        )
    finally:
        if own_session:
            active_session.close()

    return GovernedProposalRevisionWrite(
        proposal=write.proposal,
        receipt_ref=write.receipt_ref,
        previous_receipt_ref=existing.receipt_ref,
        changed_scaffold_fields=changed_fields,
        admitted_proposal_version_id=admitted.proposal_version_id,
        admitted_proposal_receipt_ref=admitted.receipt_ref,
        resulting_proposal_version_id=write.receipt_ref.split("/")[-1].replace(".json", ""),
        resulting_proposal_receipt_ref=write.receipt_ref,
        execution_allowed=False,
    )


@dataclass(frozen=True)
class GovernedReviewEventWrite:
    review_event: ReviewEvent
    receipt_ref: str
    admitted_proposal_version_id: str
    admitted_proposal_receipt_ref: str
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


def _review_event_receipt_payload(
    event: ReviewEvent,
    proposal: Proposal,
    *,
    admitted_version_id: str,
    admitted_receipt_ref: str,
    mutation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "receipt_id": f"receipt_{event.review_event_id}",
        "kind": "state_core_review_event",
        "created_at_utc": event.created_at_utc,
        "proposal_id": proposal.proposal_id,
        "proposal_receipt_ref": proposal.receipt_ref,
        "admitted_proposal_version_id": admitted_version_id,
        "admitted_proposal_receipt_ref": admitted_receipt_ref,
        "review_event": event.model_dump(mode="json"),
        "governance": {
            "execution_allowed": False,
            "not_execution_authorization": True,
            "not_investment_advice": True,
        },
    }

    if mutation_context is not None:
        payload["mutation_context"] = mutation_context

    return payload


def create_governed_review_event(
    *,
    proposal_id: str,
    kind: ReviewEventKind,
    attester: str,
    reason: str,
    expectation: ProposalVersionExpectation,
    text: str | None = None,
    attestation_ref: str | None = None,
    compare_with: str | None = None,
    source_refs: list[str] | None = None,
    mutation_context: dict[str, Any] | None = None,
    engine: Engine,
    receipt_root: str | Path,
    session: Session | None = None,
) -> GovernedReviewEventWrite:
    """Append a human review event (annotation/archive/reopen/compare_mark).

    Version binding: ``expectation`` is validated inside *session* (or a new
    Session), and the version check + domain write share one transaction.
    """
    if kind not in REVIEW_EVENT_KINDS:
        raise ValueError(f"unknown review event kind: {kind}")
    if not attester.strip() or not reason.strip():
        raise ValueError("review event requires a named human and written reason")

    own_session = session is None
    active_session = session or Session(engine, expire_on_commit=False)
    try:
        # Version check inside same session
        admitted = require_current_proposal_version_in_session(
            expectation,
            proposal_id=proposal_id,
            session=active_session,
            receipt_root=receipt_root,
        )
        proposal = active_session.get(Proposal, proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)

        if kind == "compare_mark":
            target = (compare_with or "").strip()
            if not target:
                raise ValueError("compare_mark requires a compare_with proposal id")
            if target == proposal.proposal_id:
                raise ValueError("compare_mark cannot compare a proposal with itself")
            if active_session.get(Proposal, target) is None:
                raise KeyError(target)
            compare_with = target

        created_at = _now_utc()
        review_event_id = _safe_id(
            f"rev_{kind}_{_revision_stamp()}_{uuid4().hex[:8]}"
        )
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
        receipt_path = resolve_under(
            receipt_root, "review-events", f"{receipt_id}.json"
        )
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
                for ref in [
                    proposal.receipt_ref,
                    receipt_ref,
                    *(source_refs or []),
                ]
                if ref
            ],
            bound_proposal_version_id=admitted.proposal_version_id,
            bound_proposal_receipt_ref=admitted.receipt_ref,
            content_hash=content_hash,
            created_at_utc=created_at,
            as_of_utc=created_at,
        )
        receipt_payload = _review_event_receipt_payload(
            event,
            proposal,
            admitted_version_id=admitted.proposal_version_id,
            admitted_receipt_ref=admitted.receipt_ref,
            mutation_context=mutation_context,
        )
        atomic_write_json(receipt_path, receipt_payload)
        receipt_index = _receipt_index(
            receipt_id=receipt_id,
            kind="state_core_review_event",
            path=receipt_path,
            created_at_utc=created_at,
            refs=[
                ref
                for ref in [
                    proposal.receipt_ref,
                    proposal.proposal_id,
                    *event.source_refs,
                ]
                if ref
            ],
        )

        # Write inside the same session
        active_session.add(event)
        active_session.add(receipt_index)
        active_session.flush()

        if own_session:
            active_session.commit()
    except (KeyError, ValueError):
        if own_session:
            active_session.close()
        raise
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        if own_session:
            active_session.close()
        raise
    finally:
        if own_session and not active_session.is_active:
            pass  # already committed or closed
        elif own_session:
            active_session.close()

    return GovernedReviewEventWrite(
        review_event=event,
        receipt_ref=receipt_ref,
        admitted_proposal_version_id=admitted.proposal_version_id,
        admitted_proposal_receipt_ref=admitted.receipt_ref,
    )


def _latest_archive_event(events: list[ReviewEvent]) -> ReviewEvent | None:
    toggles = [event for event in events if event.kind in ("archive", "reopen")]
    if not toggles:
        return None
    toggles.sort(key=lambda event: (event.created_at_utc, event.review_event_id))
    return toggles[-1]


def is_archived(proposal_id: str, *, engine: Engine) -> bool:
    """Derive archived state from the latest archive/reopen event (append-only history)."""
    with Session(engine) as session:
        events = list(
            session.exec(select(ReviewEvent).where(ReviewEvent.proposal_id == proposal_id))
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


def create_governed_attestation(
    *,
    proposal_id: str,
    decision: DecisionInput,
    attester: str,
    reason: str,
    expectation: ProposalVersionExpectation,
    source_refs: list[str] | None = None,
    mutation_context: dict[str, Any] | None = None,
    engine: Engine,
    receipt_root: str | Path,
    session: Session | None = None,
) -> GovernedAttestationWrite:
    """Write a human attestation; approval remains non-execution authorization.

    Version binding: ``expectation`` is validated inside *session* (or a new
    Session), and the version check + domain write share one transaction.
    """
    own_session = session is None
    active_session = session or Session(engine, expire_on_commit=False)
    try:
        # Version check inside same session
        admitted = require_current_proposal_version_in_session(
            expectation,
            proposal_id=proposal_id,
            session=active_session,
            receipt_root=receipt_root,
        )
        proposal = active_session.get(Proposal, proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)

        if decision == "approved":
            ensure_confirmable(
                kind=proposal.kind,
                evidence=proposal.evidence,
                decision_scaffold=proposal.decision_scaffold,
            )

        created_at = _now_utc()
        attestation_id = _safe_id(f"att_{_stamp()}_{uuid4().hex[:8]}")
        receipt_id = f"receipt_{attestation_id}"
        receipt_path = resolve_under(
            receipt_root, "attestations", f"{receipt_id}.json"
        )
        receipt_ref = _display_path(receipt_path)
        attestation = Attestation(
            attestation_id=attestation_id,
            proposal_id=proposal.proposal_id,
            attester=attester.strip(),
            reason=reason.strip(),
            decision=decision,
            source_refs=[
                ref
                for ref in [
                    proposal.receipt_ref,
                    receipt_ref,
                    *(source_refs or []),
                ]
                if ref
            ],
            bound_proposal_version_id=admitted.proposal_version_id,
            bound_proposal_receipt_ref=admitted.receipt_ref,
            created_at_utc=created_at,
            as_of_utc=created_at,
        )
        receipt_payload = _attestation_receipt_payload(
            attestation,
            proposal,
            receipt_id,
            admitted_version_id=admitted.proposal_version_id,
            admitted_receipt_ref=admitted.receipt_ref,
            mutation_context=mutation_context,
        )
        atomic_write_json(receipt_path, receipt_payload)
        receipt_index = _receipt_index(
            receipt_id=receipt_id,
            kind="state_core_attestation",
            path=receipt_path,
            created_at_utc=created_at,
            refs=[
                ref
                for ref in [proposal.receipt_ref, proposal.proposal_id]
                if ref
            ],
        )

        # Write inside the same session
        active_session.add(attestation)
        active_session.add(receipt_index)
        active_session.flush()

        if own_session:
            active_session.commit()
    except (KeyError, ValueError):
        if own_session:
            active_session.close()
        raise
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        if own_session:
            active_session.close()
        raise
    finally:
        if own_session and not active_session.is_active:
            pass
        elif own_session:
            active_session.close()

    return GovernedAttestationWrite(
        attestation=attestation,
        proposal=proposal,
        receipt_ref=receipt_ref,
        admitted_proposal_version_id=admitted.proposal_version_id,
        admitted_proposal_receipt_ref=admitted.receipt_ref,
        approved_is_not_execution_authorization=True,
        execution_allowed=False,
    )
