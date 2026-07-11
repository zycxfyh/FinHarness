"""B4 (see docs/reference/glossary.md): lesson -> rule-change lineage.

Project terms B4 and Ordivon are anchored in docs/reference/glossary.md.

lesson_loop.py drafts lessons from receipts but stops at "a human promotes it".
This module is the missing half: a human promotes a lesson draft into a recorded
RuleChange that carries lineage back to the lesson and, transitively, to the
receipts the lesson was derived from. A rule/threshold/checklist change is only
B4-legitimate if it is traceable to a lesson to receipts.

Shape (Ordivon, see docs/reference/glossary.md): the lesson draft is the
grounded claim; promotion is a human authorization grant (an attester is
required, never a default); the RuleChange + receipt is the observation record;
is_traceable is the closure check. The comparator is the human (B-doc section
3): AI drafts, a human promotes. Nothing here applies a change automatically —
this increment proves lineage, not enforcement.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.lesson_loop import LessonDraft
from finharness.project_paths import ROOT

RULE_CHANGE_STATE_ROOT = ROOT / "data" / "state" / "rule-changes"
RULE_CHANGE_RECEIPT_ROOT = ROOT / "data" / "receipts" / "rule-changes"

RuleChangeKind = Literal["threshold", "checklist", "allowlist", "prompt_template"]


class RuleChangePromotionError(RuntimeError):
    """Raised when a promotion cannot be authorized (e.g. no attester)."""


class RuleChange(BaseModel):
    """A rule/threshold/checklist change with lineage to its justifying lesson."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "finharness.rule_change.v1"
    rule_change_id: str
    created_at_utc: str
    rule_target: str  # e.g. "guard.hard_stop_drawdown_pct"
    change_kind: RuleChangeKind
    old_value: Any = None
    new_value: Any = None
    rationale: str
    attester: str  # the human who promoted this; never empty
    lesson_draft_id: str | None = None
    lesson_doc_ref: str | None = None
    receipt_refs: list[str] = Field(default_factory=list)
    status: Literal["active", "reverted"] = "active"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def is_traceable(change: RuleChange) -> bool:
    """B4 closure check (see docs/reference/glossary.md).

    A change is legitimate only if it traces to a lesson and, through it, to
    receipts. A change with no lesson or no receipts is a hand-fed rule change
    with no evidence behind it.
    """
    return bool(
        change.lesson_draft_id
        and change.lesson_doc_ref
        and change.receipt_refs
        and change.rationale.strip()
        and change.attester.strip()
    )


def promote_lesson_to_rule_change(
    *,
    lesson_draft: LessonDraft,
    rule_target: str,
    change_kind: RuleChangeKind,
    new_value: Any,
    rationale: str,
    attester: str,
    lesson_doc_ref: str,
    old_value: Any = None,
    state_root: Path | None = None,
    receipt_root: Path | None = None,
) -> RuleChange:
    """Human action: turn a lesson draft into a recorded rule change with lineage.

    Authorization-before-action: an attester and a rationale are mandatory; the
    receipt refs are pulled from the lesson so the change inherits lineage to the
    receipts the lesson was derived from. A change that would not be traceable is
    refused — B4 (see docs/reference/glossary.md) does not record evidence-free
    rule changes.
    """
    if not attester.strip():
        raise RuleChangePromotionError("promotion requires a human attester")
    if not rationale.strip():
        raise RuleChangePromotionError("promotion requires a written rationale")
    if not lesson_draft.receipt_refs:
        raise RuleChangePromotionError(
            "lesson draft carries no receipt refs; it cannot justify a rule change"
        )

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    change = RuleChange(
        rule_change_id=f"rulechg_{stamp}_{uuid4().hex[:8]}",
        created_at_utc=_now_utc(),
        rule_target=rule_target,
        change_kind=change_kind,
        old_value=old_value,
        new_value=new_value,
        rationale=rationale,
        attester=attester,
        lesson_draft_id=lesson_draft.draft_id,
        lesson_doc_ref=lesson_doc_ref,
        receipt_refs=list(lesson_draft.receipt_refs),
    )
    if not is_traceable(change):  # defensive; the guards above should ensure it
        raise RuleChangePromotionError("refusing to record an untraceable rule change")

    state = state_root or RULE_CHANGE_STATE_ROOT
    receipts = receipt_root or RULE_CHANGE_RECEIPT_ROOT
    payload = change.model_dump(mode="json")
    _write_json(state / f"{change.rule_change_id}.json", payload)
    _write_json(
        receipts / f"receipt_{change.rule_change_id}.json",
        {
            "receipt_id": f"receipt_{change.rule_change_id}",
            "kind": "rule_change_promotion",
            "created_at_utc": change.created_at_utc,
            "rule_change": payload,
            "lineage": {
                "lesson_draft_id": change.lesson_draft_id,
                "lesson_doc_ref": change.lesson_doc_ref,
                "receipt_count": len(change.receipt_refs),
            },
        },
    )
    return change


def load_rule_changes(state_root: Path | None = None) -> list[RuleChange]:
    state = state_root or RULE_CHANGE_STATE_ROOT
    if not state.is_dir():
        return []
    changes: list[RuleChange] = []
    for path in sorted(state.glob("rulechg_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        try:
            changes.append(RuleChange.model_validate(payload))
        except ValueError:
            continue
    return changes


def trace_rule_change(
    rule_change_id: str, *, state_root: Path | None = None
) -> dict[str, Any]:
    """Return the lineage chain: rule_change -> lesson -> receipts. The evidence
    that B4 holds for one change (see docs/reference/glossary.md)."""
    for change in load_rule_changes(state_root):
        if change.rule_change_id == rule_change_id:
            return {
                "rule_change": change.model_dump(mode="json"),
                "lesson": {
                    "lesson_draft_id": change.lesson_draft_id,
                    "lesson_doc_ref": change.lesson_doc_ref,
                },
                "receipts": change.receipt_refs,
                "traceable": is_traceable(change),
            }
    raise KeyError(rule_change_id)


def audit_untraceable(state_root: Path | None = None) -> list[str]:
    """Ids of recorded rule changes that fail the B4 lineage check.

    See docs/reference/glossary.md. This should be empty; a non-empty result is a
    governance failure to escalate to a human.
    """
    return [
        change.rule_change_id
        for change in load_rule_changes(state_root)
        if not is_traceable(change)
    ]
