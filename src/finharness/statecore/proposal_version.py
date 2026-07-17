"""Authoritative current ProposalVersion resolution from row + receipt truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session

from finharness.statecore.models import Proposal
from finharness.statecore.proposal_revisions import RevisionRecord, walk_proposal_revisions

ProposalVersionErrorCode = Literal[
    "proposal_not_found",
    "receipt_chain_invalid",
    "receipt_payload_invalid",
    "receipt_content_hash_invalid",
    "row_receipt_divergence",
    "stale_expected_version",
    "stale_expected_receipt",
    "proposal_version_conflict",
]


class ProposalVersionResolutionError(RuntimeError):
    def __init__(self, code: ProposalVersionErrorCode, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class ProposalVersionLineage:
    proposal_version_id: str
    receipt_ref: str
    content_hash: str
    supersedes_version_id: str | None


@dataclass(frozen=True)
class CurrentProposalVersion:
    proposal_id: str
    proposal_version_id: str
    receipt_ref: str
    content_hash: str
    lineage: tuple[ProposalVersionLineage, ...]


@dataclass(frozen=True)
class ProposalVersionExpectation:
    """Caller-supplied expected version pair for a governed review write."""

    proposal_id: str
    proposal_version_id: str
    receipt_ref: str


def _validated_proposal(record: RevisionRecord) -> Proposal:
    from finharness.statecore.proposals import proposal_content_hash

    try:
        proposal = Proposal.model_validate(record.proposal)
    except ValidationError as exc:
        raise ProposalVersionResolutionError(
            "receipt_payload_invalid",
            f"proposal receipt {record.receipt_ref} has an invalid Proposal payload",
        ) from exc
    expected_hash = proposal_content_hash(proposal)
    if record.content_hash != expected_hash:
        raise ProposalVersionResolutionError(
            "receipt_content_hash_invalid",
            f"proposal receipt {record.receipt_ref} content hash does not match its payload",
        )
    if not record.receipt_id:
        raise ProposalVersionResolutionError(
            "receipt_payload_invalid",
            f"proposal receipt {record.receipt_ref} has no unique receipt/version identity",
        )
    return proposal


def _resolve_row_in_session(proposal_id: str, session: Session) -> CurrentProposalVersion:
    """Resolve current version from the Proposal row inside *session*.

    This is the session-aware resolver: it reads the row from the same Session
    that will later commit domain effects, closing the TOCTOU gap.
    """
    from finharness.statecore.proposals import proposal_content_hash

    row = session.get(Proposal, proposal_id)
    if row is None:
        raise ProposalVersionResolutionError(
            "proposal_not_found", f"proposal not found: {proposal_id}"
        )
    if not row.receipt_ref:
        raise ProposalVersionResolutionError(
            "proposal_not_found", f"proposal {proposal_id} has no receipt_ref"
        )
    return CurrentProposalVersion(
        proposal_id=proposal_id,
        proposal_version_id=row.receipt_ref.split("/")[-1].replace(".json", ""),
        receipt_ref=row.receipt_ref,
        content_hash=proposal_content_hash(row),
        lineage=(),
    )


def resolve_current_proposal_version(
    proposal_id: str,
    *,
    engine: Engine,
    receipt_root: str | Path,
) -> CurrentProposalVersion:
    """Resolve current version only when DB mirror and receipt chain agree."""

    with Session(engine) as session:
        row = session.get(Proposal, proposal_id)
    if row is None:
        raise ProposalVersionResolutionError(
            "proposal_not_found", f"proposal not found: {proposal_id}"
        )

    allowed_root = Path(receipt_root).resolve()
    walk = walk_proposal_revisions(
        proposal_id,
        row.receipt_ref,
        allowed_roots=(allowed_root,),
    )
    if not walk.ok or not walk.revisions:
        anomaly = walk.anomalies[0] if walk.anomalies else None
        detail = anomaly.detail if anomaly else "proposal receipt chain is empty"
        raise ProposalVersionResolutionError("receipt_chain_invalid", detail)

    validated = [_validated_proposal(record) for record in walk.revisions]
    latest_record = walk.revisions[0]
    latest = validated[0]
    if row.receipt_ref != latest_record.receipt_ref or (
        row.model_dump(mode="json") != latest.model_dump(mode="json")
    ):
        raise ProposalVersionResolutionError(
            "row_receipt_divergence",
            f"proposal row {proposal_id} does not match current receipt payload",
        )

    lineage = tuple(
        ProposalVersionLineage(
            proposal_version_id=record.receipt_id,
            receipt_ref=record.receipt_ref,
            content_hash=str(record.content_hash),
            supersedes_version_id=(
                walk.revisions[index + 1].receipt_id
                if index + 1 < len(walk.revisions)
                else None
            ),
        )
        for index, record in enumerate(walk.revisions)
    )
    return CurrentProposalVersion(
        proposal_id=proposal_id,
        proposal_version_id=latest_record.receipt_id,
        receipt_ref=latest_record.receipt_ref,
        content_hash=str(latest_record.content_hash),
        lineage=lineage,
    )


def require_current_proposal_version(
    proposal_id: str,
    *,
    expected_version_id: str,
    expected_receipt_ref: str,
    engine: Engine,
    receipt_root: str | Path,
) -> CurrentProposalVersion:
    """Write-admission guard rejecting caller-supplied stale expectations."""

    current = resolve_current_proposal_version(
        proposal_id, engine=engine, receipt_root=receipt_root
    )
    if expected_version_id != current.proposal_version_id:
        raise ProposalVersionResolutionError(
            "stale_expected_version",
            f"expected ProposalVersion {expected_version_id} is not current",
        )
    if expected_receipt_ref != current.receipt_ref:
        raise ProposalVersionResolutionError(
            "stale_expected_receipt",
            f"expected proposal receipt {expected_receipt_ref} is not current",
        )
    return current


def require_current_proposal_version_in_session(
    expectation: ProposalVersionExpectation,
    *,
    session: Session,
) -> CurrentProposalVersion:
    """Validate ``expectation`` against the current Proposal row inside *session*.

    The row is read from the same Session that will commit domain effects, so
    the version check and the write share one transaction boundary.

    Raises ``ProposalVersionResolutionError`` with code
    ``proposal_version_conflict`` if the expectation is stale.
    """
    current = _resolve_row_in_session(expectation.proposal_id, session)

    mismatch_version = (
        expectation.proposal_version_id != current.proposal_version_id
    )
    mismatch_receipt = expectation.receipt_ref != current.receipt_ref
    if mismatch_version or mismatch_receipt:
        raise ProposalVersionResolutionError(
            "proposal_version_conflict",
            (
                f"expected ProposalVersion {expectation.proposal_version_id}"
                f" / {expectation.receipt_ref} is not current;"
                f" current is {current.proposal_version_id} / {current.receipt_ref}"
            ),
        )
    return current
