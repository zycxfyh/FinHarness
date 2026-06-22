"""Read-only Retrospective cockpit routes (S4-R3).

Surfaces existing headless retrospective assets — the latest ``annual_review`` receipt
(primary; closure fields pass through unchanged, never recomputed) plus the rule-change
state ledger as drill-down/provenance. Strictly read-only: these routes never call
``compute_annual_review`` / ``record_annual_review`` / ``promote_lesson_to_rule_change`` /
``persist_lesson_draft``, never write, and carry no execution authority.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from finharness.annual_review import load_latest_annual_review
from finharness.api.dependencies import ReceiptRootDependency
from finharness.rule_change_ledger import is_traceable, load_rule_changes

router = APIRouter(tags=["review"])


class RuleChangeView(BaseModel):
    rule_change_id: str
    rule_target: str
    change_kind: str
    status: str
    attester: str
    traceable: bool


class RetrospectiveResponse(BaseModel):
    # The latest annual_review receipt payload, passed through field-for-field (closure
    # status is taken from the receipt, never recomputed here). None when none exists.
    retrospective: dict[str, Any] | None
    rule_changes: list[RuleChangeView]
    data_gaps: list[str]
    non_claims: tuple[str, ...] = (
        "Retrospective is historical evidence only.",
        "Unclosed lessons are disclosure, not a recommendation or a rule change.",
        "Not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


@router.get("/review/retrospective", response_model=RetrospectiveResponse)
async def get_retrospective(receipt_root: ReceiptRootDependency) -> RetrospectiveResponse:
    annual_review_root = receipt_root.parent / "annual-review"
    rule_change_state_root = receipt_root.parent.parent / "state" / "rule-changes"

    retrospective, data_gaps = load_latest_annual_review(annual_review_root)

    rule_changes: list[RuleChangeView] = []
    try:
        for change in load_rule_changes(rule_change_state_root):
            rule_changes.append(
                RuleChangeView(
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

    return RetrospectiveResponse(
        retrospective=retrospective,
        rule_changes=rule_changes,
        data_gaps=data_gaps,
        execution_allowed=False,
    )
