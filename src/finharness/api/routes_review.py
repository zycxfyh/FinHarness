"""Read-only Review-System cockpit routes (S4-R3 retrospective, S4-R4 compare marks).

Thin HTTP adapters over the Review-System read model (``review_read``): the latest
``annual_review`` retrospective and the compare-marked pairs. Strictly read-only: these
routes never call ``compute_annual_review`` / ``record_annual_review`` /
``promote_lesson_to_rule_change`` / ``persist_lesson_draft`` / ``create_governed_*``,
never write, and carry no execution authority.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from finharness.api.dependencies import EngineDependency, ReceiptRootDependency
from finharness.review_read import read_compare_marks, read_retrospective

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
    # Provenance: which receipt the retrospective came from, so it is replayable.
    retrospective_receipt_ref: str | None
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
    model = read_retrospective(annual_review_root, rule_change_state_root)
    return RetrospectiveResponse(
        retrospective=model.retrospective,
        retrospective_receipt_ref=model.retrospective_receipt_ref,
        rule_changes=[
            RuleChangeView(
                rule_change_id=row.rule_change_id,
                rule_target=row.rule_target,
                change_kind=row.change_kind,
                status=row.status,
                attester=row.attester,
                traceable=row.traceable,
            )
            for row in model.rule_changes
        ],
        data_gaps=model.data_gaps,
        execution_allowed=False,
    )


class ComparePairView(BaseModel):
    proposal_id: str
    compare_with: str
    attester: str
    reason: str
    created_at_utc: str
    review_event_id: str
    proposal_exists: bool
    compare_with_exists: bool
    missing_side: str | None
    data_gaps: list[str]


class CompareMarksResponse(BaseModel):
    pairs: list[ComparePairView]
    non_claims: tuple[str, ...] = (
        "Compare marks are descriptive pairings for review, not a recommendation.",
        "Side-by-side facts do not rank or pick a candidate.",
        "Not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


@router.get("/review/compare-marks", response_model=CompareMarksResponse)
async def get_compare_marks(engine: EngineDependency) -> CompareMarksResponse:
    pairs = read_compare_marks(engine)
    return CompareMarksResponse(
        pairs=[
            ComparePairView(
                proposal_id=pair.proposal_id,
                compare_with=pair.compare_with,
                attester=pair.attester,
                reason=pair.reason,
                created_at_utc=pair.created_at_utc,
                review_event_id=pair.review_event_id,
                proposal_exists=pair.proposal_exists,
                compare_with_exists=pair.compare_with_exists,
                missing_side=pair.missing_side,
                data_gaps=pair.data_gaps,
            )
            for pair in pairs
        ],
        execution_allowed=False,
    )
