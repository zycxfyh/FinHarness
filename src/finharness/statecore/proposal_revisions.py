"""Shared replay-truth walker for governed proposal receipt revision chains.

A proposal's revision history is reconstructed by following ``receipt_ref ->
supersedes`` through the receipt files. Receipt files are the replay source of
truth: the DB index can help look a proposal up, but it cannot prove the
revision chain is intact, so this walker reads the chain and reports broken
links as structured anomalies instead of crashing.

Callers decide how to surface anomalies, which is why this module is
intentionally free of HTTP / report concerns:

* the API (`routes_proposals`) maps anomalies to typed HTTP errors;
* the annual review degrades them into human-readable data gaps.

This keeps a single, audited walk of the chain so the Phase 4 review views and
the retrospective never drift apart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from finharness.project_paths import ROOT, display_path

PROPOSAL_RECEIPT_KIND = "state_core_proposal"

RevisionAnomalyCode = Literal[
    "no_receipt_ref",
    "outside_allowed_roots",
    "missing",
    "unreadable",
    "wrong_kind",
    "no_proposal_payload",
    "wrong_proposal_id",
    "invalid_supersedes",
    "cycle",
    "too_many",
]


@dataclass(frozen=True)
class RevisionRecord:
    """One valid receipt in a proposal's revision chain (latest -> oldest)."""

    receipt_id: str
    receipt_ref: str
    created_at_utc: str
    content_hash: str | None
    supersedes: str | None
    proposal: dict[str, Any]
    revision_context: dict[str, Any]


@dataclass(frozen=True)
class RevisionAnomaly:
    """A broken link in a revision chain, carried instead of raised."""

    code: RevisionAnomalyCode
    proposal_id: str
    receipt_ref: str
    path: str
    detail: str


@dataclass
class RevisionWalk:
    """Result of walking a chain: the revisions read plus any anomaly that
    stopped the walk. The walk halts at the first anomaly, mirroring the prior
    behaviour of both call sites, so ``anomalies`` holds at most one entry."""

    revisions: list[RevisionRecord] = field(default_factory=list)
    anomalies: list[RevisionAnomaly] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.anomalies

    @property
    def count(self) -> int:
        return len(self.revisions)


def _resolve_receipt_path(
    receipt_ref: str,
    *,
    allowed_roots: tuple[Path, ...] | None,
) -> Path | None:
    """Resolve a receipt_ref (relative refs anchor to ROOT) and, when
    ``allowed_roots`` is given, reject anything that escapes them. ``None`` means
    no guard (the retrospective trusts DB-sourced refs); a guard is used by the
    API, which serves untrusted path inputs."""
    raw = Path(receipt_ref)
    candidate = raw if raw.is_absolute() else ROOT / raw
    resolved = candidate.resolve(strict=False)
    if allowed_roots is not None and not any(
        resolved.is_relative_to(root) for root in allowed_roots
    ):
        return None
    return resolved


def _read_revision(
    proposal_id: str,
    receipt_ref: str,
    *,
    allowed_roots: tuple[Path, ...] | None,
) -> tuple[RevisionRecord | None, RevisionAnomaly | None]:
    """Read and validate a single receipt in a chain.

    Returns ``(record, anomaly)``. A read/validation failure returns
    ``(None, anomaly)``; a valid receipt whose ``supersedes`` link is malformed
    returns ``(record, anomaly)`` so the record is kept while the walk stops.
    """

    def fault(code: RevisionAnomalyCode, path: str, detail: str) -> RevisionAnomaly:
        return RevisionAnomaly(
            code=code,
            proposal_id=proposal_id,
            receipt_ref=receipt_ref,
            path=path,
            detail=detail,
        )

    resolved = _resolve_receipt_path(receipt_ref, allowed_roots=allowed_roots)
    if resolved is None:
        return None, fault(
            "outside_allowed_roots",
            receipt_ref,
            f"proposal {proposal_id} revision receipt outside allowed roots: {receipt_ref}",
        )

    shown = display_path(resolved)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, fault(
            "missing", shown, f"proposal {proposal_id} revision receipt missing: {shown}"
        )
    except (json.JSONDecodeError, OSError):
        return None, fault(
            "unreadable", shown, f"proposal {proposal_id} revision receipt unreadable: {shown}"
        )

    if payload.get("kind") != PROPOSAL_RECEIPT_KIND:
        return None, fault(
            "wrong_kind",
            shown,
            f"proposal {proposal_id} revision receipt has unexpected kind: {shown}",
        )
    payload_proposal = payload.get("proposal")
    if not isinstance(payload_proposal, dict):
        return None, fault(
            "no_proposal_payload",
            shown,
            f"proposal {proposal_id} revision receipt lacks proposal payload: {shown}",
        )
    if payload_proposal.get("proposal_id") != proposal_id:
        return None, fault(
            "wrong_proposal_id",
            shown,
            f"proposal {proposal_id} revision receipt points to "
            f"{payload_proposal.get('proposal_id')}: {shown}",
        )

    supersedes_raw = payload.get("supersedes")
    record = RevisionRecord(
        receipt_id=str(payload.get("receipt_id") or ""),
        receipt_ref=receipt_ref,
        created_at_utc=str(payload.get("created_at_utc") or ""),
        content_hash=payload.get("content_hash"),
        supersedes=supersedes_raw if isinstance(supersedes_raw, str) else None,
        proposal=payload_proposal,
        revision_context=(
            payload["revision_context"]
            if isinstance(payload.get("revision_context"), dict)
            else {}
        ),
    )
    if supersedes_raw is not None and not isinstance(supersedes_raw, str):
        return record, fault(
            "invalid_supersedes",
            shown,
            f"proposal {proposal_id} revision receipt has invalid supersedes: {shown}",
        )
    return record, None


def walk_proposal_revisions(
    proposal_id: str,
    receipt_ref: str | None,
    *,
    allowed_roots: tuple[Path, ...] | None = None,
    max_revisions: int = 100,
) -> RevisionWalk:
    """Walk ``receipt_ref -> supersedes`` for ``proposal_id``.

    Returns the revisions read (latest first) and, if the chain is broken, the
    single anomaly that stopped it. The current receipt is always included
    before its ``supersedes`` link is evaluated, so a malformed link still keeps
    the record that pointed at it.
    """
    walk = RevisionWalk()
    if not receipt_ref:
        walk.anomalies.append(
            RevisionAnomaly(
                code="no_receipt_ref",
                proposal_id=proposal_id,
                receipt_ref="",
                path="",
                detail=f"proposal {proposal_id} has no receipt_ref",
            )
        )
        return walk

    seen: set[str] = set()
    current: str | None = receipt_ref
    while current:
        if current in seen:
            walk.anomalies.append(
                RevisionAnomaly(
                    code="cycle",
                    proposal_id=proposal_id,
                    receipt_ref=current,
                    path=current,
                    detail=f"proposal {proposal_id} revision chain cycle at {current}",
                )
            )
            break
        if walk.count >= max_revisions:
            walk.anomalies.append(
                RevisionAnomaly(
                    code="too_many",
                    proposal_id=proposal_id,
                    receipt_ref=current,
                    path=current,
                    detail=f"proposal {proposal_id} revision chain exceeds {max_revisions}",
                )
            )
            break
        seen.add(current)

        record, anomaly = _read_revision(proposal_id, current, allowed_roots=allowed_roots)
        if record is not None:
            walk.revisions.append(record)
            # Follow the validated (str-or-None) supersedes link; "" / None ends.
            current = record.supersedes
        else:
            current = None
        if anomaly is not None:
            walk.anomalies.append(anomaly)
            break
    return walk
