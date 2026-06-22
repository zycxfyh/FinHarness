"""Annual (period) decision retrospective over the state core (north star 阶段 3, B0 Q7).

A read-only **report** (not an allocation candidate): it synthesizes existing state —
governed proposals + their revision receipts, human attestations, persisted lesson
drafts, and the rule-change ledger — into a dated retrospective receipt. It answers
"over this period, what decisions did I face, what did I decide, what evolved, and
which lessons closed the loop into rules".

Boundaries: descriptive only, ``execution_allowed=false``; it reuses the
``daily_brief`` compute/record pattern, does not write a ``Proposal`` and is not an
allocation detector. B4 lesson-to-rule closure is **reported, never automated** —
this module changes no rule. Receipt read failures (missing/corrupt) are disclosed
as data gaps rather than crashing the report.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.lesson_loop import (
    DEFAULT_RECEIPT_SOURCES,
    LESSON_RECEIPT_ROOT,
    ReceiptDigest,
    build_observations,
    build_proposed_rule_changes,
    scan_receipts,
)
from finharness.market_data import ROOT, display_path
from finharness.rule_change_ledger import audit_untraceable, is_traceable, load_rule_changes
from finharness.statecore.models import Attestation, Proposal, ReceiptIndex, utc_now_iso
from finharness.statecore.proposal_revisions import walk_proposal_revisions
from finharness.statecore.receipt_io import atomic_write_json
from finharness.statecore.store import upsert_records

ANNUAL_REVIEW_KIND = "annual_review"
DEFAULT_ANNUAL_REVIEW_RECEIPT_ROOT = ROOT / "data" / "receipts" / "annual-review"
NON_CLAIMS = (
    "Descriptive decision retrospective over mirrored state.",
    "Not investment, tax, or accounting advice.",
    "Reports lesson-to-rule closure; it does not change any rule itself.",
    "Not execution authorization.",
)


class AnnualReview(BaseModel):
    as_of_date: str
    period_start: str
    period_end: str
    period_label: str
    candidate_count: int
    candidates_by_kind: dict[str, int]
    open_count: int
    attested_count: int
    approved_count: int
    rejected_count: int
    candidates_with_revisions: int
    lesson_receipts_scanned: int
    lesson_observations: tuple[str, ...]
    proposed_rule_changes: tuple[str, ...]
    lessons_total: int
    lessons_closed: int
    lessons_open: tuple[str, ...]
    untraceable_rule_changes: tuple[str, ...]
    data_gaps: tuple[str, ...]
    non_claims: tuple[str, ...] = NON_CLAIMS
    execution_allowed: bool = False


def _date_of(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _resolve_period(as_of_date: date, year: int | None) -> tuple[date, date, str]:
    """Default is a rolling 12-month window; ``year`` selects a calendar year."""
    if year is not None:
        return date(year, 1, 1), date(year, 12, 31), str(year)
    start = date.fromordinal(as_of_date.toordinal() - 365)
    return start, as_of_date, f"12 months to {as_of_date.isoformat()}"


def _safe(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)


def _proposal_revision_count(
    proposal: Proposal,
    *,
    data_gaps: list[str],
    max_revisions: int = 100,
) -> int:
    """Count valid proposal receipt revisions, degrading broken links to gaps.

    Delegates the chain walk to the shared replay-truth walker so this report and
    the API revision view never diverge. The retrospective trusts DB-sourced
    refs, so no path guard is applied; every anomaly becomes a data gap.
    """
    walk = walk_proposal_revisions(
        proposal.proposal_id,
        proposal.receipt_ref,
        max_revisions=max_revisions,
    )
    for anomaly in walk.anomalies:
        data_gaps.append(anomaly.detail)
    return walk.count


def _receipt_digest_date(digest: ReceiptDigest) -> date | None:
    return _date_of(digest.created_at_utc)


def _lesson_signals(
    *,
    lesson_scan_root: Path | None,
    lesson_scan_sources: tuple[str, ...],
    period_start: date,
    period_end: date,
) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
    """Build deterministic lesson-loop signals without drafting a lesson."""
    scan_anchor = max(datetime.now(UTC).date(), period_end)
    window_days = max(1, (scan_anchor - period_start).days + 1)
    digests = [
        digest
        for digest in scan_receipts(
            root=lesson_scan_root,
            sources=lesson_scan_sources,
            window_days=window_days,
        )
        if (created := _receipt_digest_date(digest)) is not None
        and period_start <= created <= period_end
    ]
    return (
        len(digests),
        tuple(build_observations(digests)),
        tuple(build_proposed_rule_changes(digests)),
    )


def _lesson_closure(
    *,
    lesson_receipt_root: Path,
    rule_change_state_root: Path | None,
    period_start: date,
    period_end: date,
    data_gaps: list[str],
) -> tuple[int, int, list[str]]:
    """Closure of persisted lessons via the human-promoted rule-change ledger.

    A lesson is closed when a recorded ``RuleChange`` carries its ``lesson_draft_id``.
    This reads persisted lesson receipts and the ledger only; it never drafts or
    promotes anything.
    """
    promoted_by_lesson: dict[str, list[date]] = {}
    for change in load_rule_changes(rule_change_state_root):
        if not change.lesson_draft_id:
            continue
        created = _date_of(change.created_at_utc)
        if created is None:
            data_gaps.append(
                f"rule change {change.rule_change_id} has no parseable created_at_utc"
            )
            continue
        if created > period_end:
            continue
        if is_traceable(change):
            promoted_by_lesson.setdefault(change.lesson_draft_id, []).append(created)

    lessons_total = 0
    lessons_closed = 0
    lessons_open: list[str] = []
    if lesson_receipt_root.is_dir():
        for path in sorted(lesson_receipt_root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data_gaps.append(f"lesson receipt unreadable: {display_path(path)}")
                continue
            created = _date_of(str(payload.get("created_at_utc") or ""))
            if created is None or not (period_start <= created <= period_end):
                continue
            lessons_total += 1
            draft_id = str(payload.get("draft_id") or "")
            promoted_dates = promoted_by_lesson.get(draft_id, [])
            if draft_id and any(created <= promoted <= period_end for promoted in promoted_dates):
                lessons_closed += 1
            else:
                lessons_open.append(draft_id or display_path(path))
    return lessons_total, lessons_closed, lessons_open


def _untraceable_rule_changes(
    *,
    rule_change_state_root: Path | None,
    period_end: date,
    data_gaps: list[str],
) -> tuple[str, ...]:
    """Untraceable rule changes visible by period end."""
    untraceable_ids = set(audit_untraceable(rule_change_state_root))
    result: list[str] = []
    for change in load_rule_changes(rule_change_state_root):
        if change.rule_change_id not in untraceable_ids:
            continue
        created = _date_of(change.created_at_utc)
        if created is None:
            data_gaps.append(
                f"rule change {change.rule_change_id} has no parseable created_at_utc"
            )
            continue
        if created <= period_end:
            result.append(change.rule_change_id)
    return tuple(result)


def compute_annual_review(
    engine: Engine,
    *,
    as_of_date: date | None = None,
    year: int | None = None,
    lesson_receipt_root: Path | None = None,
    lesson_scan_root: Path | None = None,
    lesson_scan_sources: tuple[str, ...] = DEFAULT_RECEIPT_SOURCES,
    rule_change_state_root: Path | None = None,
) -> AnnualReview:
    """Pure: synthesize a read-only decision retrospective for the period."""
    reference = as_of_date or datetime.now(UTC).date()
    period_start, period_end, period_label = _resolve_period(reference, year)
    data_gaps: list[str] = []

    with Session(engine) as session:
        proposals = list(session.exec(select(Proposal)).all())
        attestations = list(session.exec(select(Attestation)).all())

    in_period: list[Proposal] = []
    for proposal in proposals:
        created = _date_of(proposal.created_at_utc)
        if created is None:
            data_gaps.append(f"proposal {proposal.proposal_id} has no parseable created_at_utc")
            continue
        if period_start <= created <= period_end:
            in_period.append(proposal)

    attestations_by_proposal: dict[str, list[Attestation]] = {}
    for attestation in attestations:
        attestations_by_proposal.setdefault(attestation.proposal_id, []).append(attestation)

    open_count = attested_count = approved_count = rejected_count = 0
    candidates_with_revisions = 0
    for proposal in in_period:
        proposal_attestations = attestations_by_proposal.get(proposal.proposal_id, [])
        if proposal_attestations:
            attested_count += 1
            latest = max(proposal_attestations, key=lambda item: item.created_at_utc)
            if latest.decision == "approved":
                approved_count += 1
            elif latest.decision == "rejected":
                rejected_count += 1
        else:
            open_count += 1
        revision_count = _proposal_revision_count(proposal, data_gaps=data_gaps)
        if revision_count > 1:
            candidates_with_revisions += 1

    lesson_receipts_scanned, lesson_observations, proposed_rule_changes = _lesson_signals(
        lesson_scan_root=lesson_scan_root,
        lesson_scan_sources=lesson_scan_sources,
        period_start=period_start,
        period_end=period_end,
    )
    lessons_total, lessons_closed, lessons_open = _lesson_closure(
        lesson_receipt_root=lesson_receipt_root or LESSON_RECEIPT_ROOT,
        rule_change_state_root=rule_change_state_root,
        period_start=period_start,
        period_end=period_end,
        data_gaps=data_gaps,
    )
    untraceable = _untraceable_rule_changes(
        rule_change_state_root=rule_change_state_root,
        period_end=period_end,
        data_gaps=data_gaps,
    )

    return AnnualReview(
        as_of_date=reference.isoformat(),
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        period_label=period_label,
        candidate_count=len(in_period),
        candidates_by_kind=dict(Counter(proposal.kind for proposal in in_period)),
        open_count=open_count,
        attested_count=attested_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        candidates_with_revisions=candidates_with_revisions,
        lesson_receipts_scanned=lesson_receipts_scanned,
        lesson_observations=lesson_observations,
        proposed_rule_changes=proposed_rule_changes,
        lessons_total=lessons_total,
        lessons_closed=lessons_closed,
        lessons_open=tuple(lessons_open),
        untraceable_rule_changes=untraceable,
        data_gaps=tuple(data_gaps),
    )


def record_annual_review(
    engine: Engine,
    *,
    receipt_root: str | Path = DEFAULT_ANNUAL_REVIEW_RECEIPT_ROOT,
    as_of_date: date | None = None,
    year: int | None = None,
    lesson_receipt_root: Path | None = None,
    lesson_scan_root: Path | None = None,
    lesson_scan_sources: tuple[str, ...] = DEFAULT_RECEIPT_SOURCES,
    rule_change_state_root: Path | None = None,
) -> tuple[AnnualReview, str]:
    """Compute the retrospective and write it as a dated receipt (one per period)."""
    review = compute_annual_review(
        engine,
        as_of_date=as_of_date,
        year=year,
        lesson_receipt_root=lesson_receipt_root,
        lesson_scan_root=lesson_scan_root,
        lesson_scan_sources=lesson_scan_sources,
        rule_change_state_root=rule_change_state_root,
    )
    receipt_id = f"receipt_annual_review_{_safe(review.period_label)}"
    receipt_path = Path(receipt_root) / f"{receipt_id}.json"
    receipt_ref = display_path(receipt_path)
    payload: dict[str, Any] = {
        "receipt_id": receipt_id,
        "kind": ANNUAL_REVIEW_KIND,
        "created_at_utc": datetime.now(UTC).isoformat(),
        **review.model_dump(),
    }
    atomic_write_json(receipt_path, payload)
    receipt_index = ReceiptIndex(
        receipt_id=receipt_id,
        kind=ANNUAL_REVIEW_KIND,
        path=receipt_ref,
        created_at_utc=utc_now_iso(),
        source_refs=[],
        refs=[],
    )
    upsert_records([receipt_index], engine=engine)
    return review, receipt_ref


def load_latest_annual_review(
    annual_review_root: str | Path = DEFAULT_ANNUAL_REVIEW_RECEIPT_ROOT,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Read-only: return the latest annual_review receipt payload + disclosed gaps.

    Selection: kind == ANNUAL_REVIEW_KIND, newest by created_at_utc, tie-broken by
    filename. An unreadable/corrupt receipt becomes a disclosed gap (never a crash); a
    missing directory or no matching receipt returns (None, gaps). This is a pure read —
    it never computes or writes an annual review.
    """
    root = Path(annual_review_root)
    gaps: list[str] = []
    if not root.exists():
        return None, gaps
    candidates: list[tuple[str, str, dict[str, Any]]] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            gaps.append(f"unreadable annual-review receipt: {path.name}")
            continue
        if not isinstance(payload, dict) or payload.get("kind") != ANNUAL_REVIEW_KIND:
            continue
        candidates.append((str(payload.get("created_at_utc") or ""), path.name, payload))
    if not candidates:
        return None, gaps
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[-1][2], gaps
