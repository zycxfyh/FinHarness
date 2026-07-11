"""Loop 4 v0: draft lesson candidates from accumulated receipts.

The slow learning loop. AI (or a deterministic summarizer) only DRAFTS lesson
candidates from receipt evidence; a human promotes drafts into rule changes.
Per the loop-topology decision (docs/think/2026-06-12-target-state-b-and-loop-
topology.md), the comparator of this loop is the human, because LLM-driven
self-improvement is the least mature loop form. Every draft carries lineage to
the receipts it was derived from.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.project_paths import ROOT, display_path

LESSON_DRAFT_DOC_ROOT = ROOT / "docs" / "lessons" / "drafts"
LESSON_RECEIPT_ROOT = ROOT / "data" / "receipts" / "lessons"

DEFAULT_RECEIPT_SOURCES = (
    "data/receipts/post-trade",
    "data/receipts/executions",
    "data/receipts/risk-gates",
    "data/receipts/alpaca-paper",
    "data/receipts/hypotheses",
    "data/receipts/validations",
)


class ReceiptDigest(BaseModel):
    """One scanned receipt reduced to lesson-relevant facts."""

    model_config = ConfigDict(frozen=True)

    receipt_ref: str
    kind: str
    created_at_utc: str
    status: str
    quality_ok: bool | None = None
    final_status: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)


class LessonDraft(BaseModel):
    """A lesson candidate awaiting human review and promotion."""

    model_config = ConfigDict(frozen=True)

    draft_id: str
    created_at_utc: str
    window_days: int
    receipts_scanned: int
    sources: list[str]
    status_counts: dict[str, int]
    quality_failure_count: int
    top_blocking_reasons: list[tuple[str, int]]
    observations: list[str]
    proposed_rule_changes: list[str]
    llm_narrative: str | None = None
    llm_provider: str | None = None
    receipt_refs: list[str]
    promotion_state: str = "draft"
    promotion_rule: str = (
        "A human must review this draft, edit or reject it, and only then move "
        "it to docs/lessons/ as a dated lesson with the rule changes it caused."
    )


def _receipt_created_at(payload: dict[str, Any]) -> str:
    return str(
        payload.get("created_at_utc")
        or payload.get("timestamp_utc")
        or payload.get("as_of_utc")
        or ""
    )


def _within_window(created_at: str, *, cutoff: datetime) -> bool:
    if not created_at:
        return False
    try:
        stamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp >= cutoff


def digest_receipt(path: Path, payload: dict[str, Any]) -> ReceiptDigest:
    snapshot = payload.get("snapshot") or {}
    quality = snapshot.get("quality") or payload.get("quality") or {}
    blocking: list[str] = []
    for decision in snapshot.get("decisions", []):
        blocking.extend(decision.get("blocking_reasons", []))
    for event in snapshot.get("events", []):
        reason = (event.get("raw_event") or {}).get("reason")
        if event.get("event_type") == "blocked" and reason:
            blocking.append(str(reason))
    return ReceiptDigest(
        receipt_ref=display_path(path),
        kind=str(payload.get("kind") or payload.get("broker") or path.parent.name),
        created_at_utc=_receipt_created_at(payload),
        status=str(payload.get("status") or "unknown"),
        quality_ok=quality.get("ok"),
        final_status=snapshot.get("final_status"),
        blocking_reasons=blocking,
    )


def scan_receipts(
    *,
    root: Path | None = None,
    sources: tuple[str, ...] = DEFAULT_RECEIPT_SOURCES,
    window_days: int = 14,
) -> list[ReceiptDigest]:
    base = root or ROOT
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    digests: list[ReceiptDigest] = []
    for source in sources:
        directory = base / source
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            digest = digest_receipt(path, payload)
            if _within_window(digest.created_at_utc, cutoff=cutoff):
                digests.append(digest)
    return digests


def build_observations(digests: list[ReceiptDigest]) -> list[str]:
    observations: list[str] = []
    if not digests:
        observations.append(
            "No receipts in the window: the loops produced no evidence to learn "
            "from. The lesson may be about cadence, not trading."
        )
        return observations
    failures = [item for item in digests if item.quality_ok is False]
    if failures:
        observations.append(
            f"{len(failures)} of {len(digests)} receipts failed quality gates; "
            "review whether the failures share one root cause."
        )
    blocked = Counter(
        reason for item in digests for reason in item.blocking_reasons
    ).most_common(3)
    for reason, count in blocked:
        observations.append(f"Blocking reason seen {count}x: {reason}")
    statuses = Counter(item.final_status for item in digests if item.final_status)
    if statuses:
        summary = ", ".join(f"{key}={value}" for key, value in statuses.most_common())
        observations.append(f"Final status distribution: {summary}")
    return observations


def build_proposed_rule_changes(digests: list[ReceiptDigest]) -> list[str]:
    """Seed human-reviewable rule-change candidates from repeated evidence.

    These are deliberately strings, not applied rules. Loop 4's comparator is a
    human; this function only points at patterns that may deserve promotion via
    rule_change_ledger.py.
    """
    proposals: list[str] = []
    if not digests:
        return proposals

    failures = [item for item in digests if item.quality_ok is False]
    statuses = Counter(item.final_status for item in digests if item.final_status)
    blocking = Counter(reason for item in digests for reason in item.blocking_reasons)

    lineage_or_quality_failures = len(failures) + statuses.get("lineage_failed", 0)
    if lineage_or_quality_failures:
        proposals.append(
            "checklist: lineage.required — "
            f"{lineage_or_quality_failures} lineage/quality failure pattern(s) "
            "found; require human repair before promoting the affected lesson."
        )

    partial_fill_count = sum(
        count for status, count in statuses.items() if "partial_fill" in status
    )
    if partial_fill_count:
        proposals.append(
            "checklist: post_trade.partial_fill_review — "
            f"{partial_fill_count} partial-fill outcome(s) found; require manual "
            "post-trade review before changing sizing or execution rules."
        )

    rejection_count = sum(
        count for status, count in statuses.items() if "rejected" in status
    )
    if rejection_count:
        proposals.append(
            "checklist: post_trade.rejection_review — "
            f"{rejection_count} rejected outcome(s) found; inspect broker or "
            "paper-adapter rejection reasons before retrying the same path."
        )

    human_attestation_blocks = sum(
        count
        for reason, count in blocking.items()
        if "human review attestation" in reason.lower()
    )
    if human_attestation_blocks >= 2:
        proposals.append(
            "checklist: risk_gate.human_attestation — "
            f"human-review attestation blocked {human_attestation_blocks}x; "
            "keep the gate visible and review whether the handoff needs clearer "
            "wording."
        )

    live_boundary_blocks = sum(
        count
        for reason, count in blocking.items()
        if "live mode" in reason.lower() or "live execution" in reason.lower()
    )
    if live_boundary_blocks >= 2:
        proposals.append(
            "allowlist: live_execution.boundary — "
            f"live-boundary blocks appeared {live_boundary_blocks}x; keep "
            "live-write expansion behind an explicit proposal and human review."
        )

    for reason, count in blocking.most_common(5):
        lowered = reason.lower()
        if (
            count < 2
            or "human review attestation" in lowered
            or "live mode" in lowered
            or "live execution" in lowered
        ):
            continue
        proposals.append(
            "checklist: repeated_blocking_reason.review — "
            f"blocking reason seen {count}x: {reason}"
        )

    return proposals


def build_lesson_prompt(draft: LessonDraft) -> str:
    stats = json.dumps(
        {
            "receipts_scanned": draft.receipts_scanned,
            "status_counts": draft.status_counts,
            "quality_failure_count": draft.quality_failure_count,
            "top_blocking_reasons": draft.top_blocking_reasons,
            "observations": draft.observations,
            "proposed_rule_changes": draft.proposed_rule_changes,
        },
        ensure_ascii=False,
        indent=1,
    )
    return (
        "You are drafting LESSON CANDIDATES for a trading-research harness from "
        "receipt statistics. You are a drafter, not a decision maker: a human "
        "reviews and may reject everything. Do not recommend trades. Do not "
        "claim anything is validated. Focus on process: gates, evidence "
        "quality, cadence, and failure patterns.\n\n"
        f"Receipt statistics for the last {draft.window_days} days:\n{stats}\n\n"
        "Write 2-4 short lesson candidates. For each: what the evidence shows, "
        "what process rule or threshold it suggests changing, and what would "
        "falsify the lesson. Plain text, no JSON."
    )


def draft_lessons(
    *,
    root: Path | None = None,
    window_days: int = 14,
    use_llm: bool = False,
    sources: tuple[str, ...] = DEFAULT_RECEIPT_SOURCES,
) -> LessonDraft:
    digests = scan_receipts(root=root, sources=sources, window_days=window_days)
    failures = [item for item in digests if item.quality_ok is False]
    blocked = Counter(
        reason for item in digests for reason in item.blocking_reasons
    ).most_common(5)
    draft = LessonDraft(
        draft_id=f"lesson_draft_{uuid4().hex[:12]}",
        created_at_utc=datetime.now(UTC).isoformat(),
        window_days=window_days,
        receipts_scanned=len(digests),
        sources=list(sources),
        status_counts=dict(Counter(item.status for item in digests)),
        quality_failure_count=len(failures),
        top_blocking_reasons=[(reason, count) for reason, count in blocked],
        observations=build_observations(digests),
        proposed_rule_changes=build_proposed_rule_changes(digests),
        receipt_refs=[item.receipt_ref for item in digests][:100],
    )
    if use_llm and digests:
        from finharness.hermes_bridge import HermesBridgeError, run_hermes_single_query

        try:
            narrative = run_hermes_single_query(build_lesson_prompt(draft))
            draft = draft.model_copy(
                update={"llm_narrative": narrative, "llm_provider": "hermes-agent"}
            )
        except HermesBridgeError as exc:
            draft = draft.model_copy(
                update={"llm_narrative": None, "llm_provider": f"hermes-agent failed: {exc}"}
            )
    return draft


def render_markdown(draft: LessonDraft) -> str:
    lines = [
        f"# Lesson Draft: {draft.draft_id}",
        "",
        f"Date: {draft.created_at_utc}",
        f"Window: last {draft.window_days} days",
        f"Receipts scanned: {draft.receipts_scanned}",
        "Status: DRAFT — not a lesson until a human promotes it.",
        "",
        "## Evidence",
        "",
        f"Status counts: `{json.dumps(draft.status_counts, ensure_ascii=False)}`",
        f"Quality failures: {draft.quality_failure_count}",
        "",
        "## Observations (deterministic)",
        "",
    ]
    lines.extend(f"- {item}" for item in draft.observations)
    if draft.proposed_rule_changes:
        lines.extend(
            [
                "",
                "## Proposed Rule Changes (draft seeds, not applied)",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in draft.proposed_rule_changes)
    if draft.llm_narrative:
        lines.extend(
            [
                "",
                "## Lesson candidates (LLM draft, unreviewed)",
                "",
                draft.llm_narrative,
            ]
        )
    lines.extend(
        [
            "",
            "## Promotion",
            "",
            draft.promotion_rule,
            "",
            "## Source receipts",
            "",
        ]
    )
    lines.extend(f"- {ref}" for ref in draft.receipt_refs[:30])
    if len(draft.receipt_refs) > 30:
        lines.append(f"- ... and {len(draft.receipt_refs) - 30} more")
    return "\n".join(lines) + "\n"


def persist_lesson_draft(
    draft: LessonDraft,
    *,
    doc_root: Path | None = None,
    receipt_root: Path | None = None,
) -> dict[str, str]:
    docs = doc_root or LESSON_DRAFT_DOC_ROOT
    receipts = receipt_root or LESSON_RECEIPT_ROOT
    docs.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    doc_path = docs / f"{day}-{draft.draft_id}.md"
    receipt_path = receipts / f"{draft.draft_id}.json"
    doc_path.write_text(render_markdown(draft), encoding="utf-8")
    receipt_path.write_text(
        json.dumps(draft.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return {"doc_ref": display_path(doc_path), "receipt_ref": display_path(receipt_path)}
