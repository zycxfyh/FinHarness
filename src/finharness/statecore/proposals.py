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
from sqlmodel import Session

from finharness.market_data import ROOT
from finharness.statecore.models import Attestation, Proposal, ReceiptIndex
from finharness.statecore.receipt_io import atomic_write_json, remove_file_best_effort
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
) -> str:
    """Stable hash of a proposal's substantive content (excludes timestamps/ids).

    Two writes with identical content hash to the same value, so an idempotent
    re-scan that sees no change does not append a redundant receipt revision.
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
    content_hash = _content_hash(
        kind=kind.strip(),
        claim=claim.strip(),
        evidence=final_evidence,
        assumptions=final_assumptions,
        limitations=final_limitations,
        non_claims=final_non_claims,
        source_refs=final_source_refs,
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
    receipt_path = Path(receipt_root) / "proposals" / f"{receipt_id}.json"
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

    created_at = _now_utc()
    attestation_id = _safe_id(f"att_{_stamp()}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{attestation_id}"
    receipt_path = Path(receipt_root) / "attestations" / f"{receipt_id}.json"
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
