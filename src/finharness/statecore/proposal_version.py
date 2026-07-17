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
    "expectation_proposal_id_mismatch",
]


class ProposalVersionResolutionError(RuntimeError):
    """Structured version-resolution error carrying expected + current context."""

    def __init__(
        self,
        code: ProposalVersionErrorCode,
        detail: str,
        *,
        proposal_id: str = "",
        expected_version_id: str = "",
        expected_receipt_ref: str = "",
        current_version_id: str = "",
        current_receipt_ref: str = "",
    ) -> None:
        super().__init__(detail)
        self.code = code
        self.proposal_id = proposal_id
        self.expected_version_id = expected_version_id
        self.expected_receipt_ref = expected_receipt_ref
        self.current_version_id = current_version_id
        self.current_receipt_ref = current_receipt_ref


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


# -- shared receipt-backed resolver -----------------------------------


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


def _resolve_current_proposal_version_from_row(
    row: Proposal,
    *,
    receipt_root: str | Path,
) -> CurrentProposalVersion:
    """Resolve the current version from a Proposal row using full receipt-chain validation.

    This is the single shared entry-point for version resolution — both the
    session-aware and public-API paths delegate here.  It walks the proposal
    receipt chain, validates every receipt, checks content hashes, and
    verifies the DB row matches the latest receipt snapshot.
    """
    if not row.receipt_ref:
        raise ProposalVersionResolutionError(
            "proposal_not_found",
            f"proposal {row.proposal_id} has no receipt_ref",
            proposal_id=row.proposal_id,
        )

    allowed_root = Path(receipt_root).resolve()
    walk = walk_proposal_revisions(
        row.proposal_id,
        row.receipt_ref,
        allowed_roots=(allowed_root,),
    )
    if not walk.ok or not walk.revisions:
        anomaly = walk.anomalies[0] if walk.anomalies else None
        detail = anomaly.detail if anomaly else "proposal receipt chain is empty"
        raise ProposalVersionResolutionError(
            "receipt_chain_invalid",
            detail,
            proposal_id=row.proposal_id,
        )

    validated = [_validated_proposal(record) for record in walk.revisions]
    latest_record = walk.revisions[0]
    latest = validated[0]
    if row.receipt_ref != latest_record.receipt_ref or (
        row.model_dump(mode="json") != latest.model_dump(mode="json")
    ):
        raise ProposalVersionResolutionError(
            "row_receipt_divergence",
            f"proposal row {row.proposal_id} does not match current receipt payload",
            proposal_id=row.proposal_id,
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
        proposal_id=row.proposal_id,
        proposal_version_id=latest_record.receipt_id,
        receipt_ref=latest_record.receipt_ref,
        content_hash=str(latest_record.content_hash),
        lineage=lineage,
    )


# -- public resolvers -------------------------------------------------


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
            "proposal_not_found",
            f"proposal not found: {proposal_id}",
            proposal_id=proposal_id,
        )
    return _resolve_current_proposal_version_from_row(row, receipt_root=receipt_root)


def resolve_current_proposal_version_in_session(
    proposal_id: str,
    *,
    session: Session,
    receipt_root: str | Path,
) -> CurrentProposalVersion:
    """Resolve current version inside *session* using full receipt-chain validation.

    Reads the Proposal row from the same Session that will later commit domain
    effects, then delegates to the shared receipt-backed resolver.
    """
    row = session.get(Proposal, proposal_id)
    if row is None:
        raise ProposalVersionResolutionError(
            "proposal_not_found",
            f"proposal not found: {proposal_id}",
            proposal_id=proposal_id,
        )
    return _resolve_current_proposal_version_from_row(row, receipt_root=receipt_root)


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
            "proposal_version_conflict",
            f"expected ProposalVersion {expected_version_id} is not current",
            proposal_id=proposal_id,
            expected_version_id=expected_version_id,
            expected_receipt_ref=expected_receipt_ref,
            current_version_id=current.proposal_version_id,
            current_receipt_ref=current.receipt_ref,
        )
    if expected_receipt_ref != current.receipt_ref:
        raise ProposalVersionResolutionError(
            "proposal_version_conflict",
            f"expected proposal receipt {expected_receipt_ref} is not current",
            proposal_id=proposal_id,
            expected_version_id=expected_version_id,
            expected_receipt_ref=expected_receipt_ref,
            current_version_id=current.proposal_version_id,
            current_receipt_ref=current.receipt_ref,
        )
    return current


def require_current_proposal_version_in_session(
    expectation: ProposalVersionExpectation,
    *,
    proposal_id: str,
    session: Session,
    receipt_root: str | Path,
) -> CurrentProposalVersion:
    """Validate ``expectation`` against the current Proposal row inside *session*.

    The row is read from the same Session that will commit domain effects, so
    the version check and the write share one transaction boundary.

    Raises ``ProposalVersionResolutionError`` with code
    ``proposal_version_conflict`` if the expectation is stale.

    Raises ``expectation_proposal_id_mismatch`` if ``expectation.proposal_id``
    does not equal *proposal_id*.
    """
    if expectation.proposal_id != proposal_id:
        raise ProposalVersionResolutionError(
            "expectation_proposal_id_mismatch",
            (
                f"expectation targets proposal {expectation.proposal_id}"
                f" but route targets {proposal_id}"
            ),
            proposal_id=proposal_id,
            expected_version_id=expectation.proposal_version_id,
            expected_receipt_ref=expectation.receipt_ref,
        )

    current = resolve_current_proposal_version_in_session(
        proposal_id, session=session, receipt_root=receipt_root
    )

    mismatch_version = expectation.proposal_version_id != current.proposal_version_id
    mismatch_receipt = expectation.receipt_ref != current.receipt_ref
    if mismatch_version or mismatch_receipt:
        raise ProposalVersionResolutionError(
            "proposal_version_conflict",
            (
                f"expected ProposalVersion {expectation.proposal_version_id}"
                f" / {expectation.receipt_ref} is not current;"
                f" current is {current.proposal_version_id} / {current.receipt_ref}"
            ),
            proposal_id=proposal_id,
            expected_version_id=expectation.proposal_version_id,
            expected_receipt_ref=expectation.receipt_ref,
            current_version_id=current.proposal_version_id,
            current_receipt_ref=current.receipt_ref,
        )
    return current
