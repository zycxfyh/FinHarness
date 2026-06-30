"""Read-only risk register routes."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from finharness.api.dependencies import EngineDependency, ReceiptRootDependency
from finharness.risk_register import RISK_REGISTER_NON_CLAIMS, read_review_risk_register

router = APIRouter(tags=["risk"])


class RiskRegisterItemView(BaseModel):
    risk_id: str
    risk_kind: str
    title: str
    description: str
    severity_hint: str
    status: str
    source_type: str
    related_proposal_ids: list[str]
    evidence_status: str
    risk_reasons: list[str]
    data_gaps: list[str]
    open_questions: list[str]
    source_refs: list[str]
    receipt_refs: list[str]
    next_actions: list[str]
    non_claims: tuple[str, ...] = RISK_REGISTER_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class RiskRegisterResponse(BaseModel):
    items: list[RiskRegisterItemView]
    non_claims: tuple[str, ...] = RISK_REGISTER_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


@router.get("/risk/register", response_model=RiskRegisterResponse)
async def get_risk_register(
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    limit: int = Query(default=100, ge=1, le=200),
    include_closed: bool = False,
) -> RiskRegisterResponse:
    register = read_review_risk_register(
        engine,
        receipt_root=receipt_root,
        limit=limit,
        include_closed=include_closed,
    )
    return RiskRegisterResponse(
        items=[
            RiskRegisterItemView(
                risk_id=item.risk_id,
                risk_kind=item.risk_kind,
                title=item.title,
                description=item.description,
                severity_hint=item.severity_hint,
                status=item.status,
                source_type=item.source_type,
                related_proposal_ids=item.related_proposal_ids,
                evidence_status=item.evidence_status,
                risk_reasons=item.risk_reasons,
                data_gaps=item.data_gaps,
                open_questions=item.open_questions,
                source_refs=item.source_refs,
                receipt_refs=item.receipt_refs,
                next_actions=item.next_actions,
                execution_allowed=False,
                authority_transition=False,
            )
            for item in register.items
        ],
        execution_allowed=False,
        authority_transition=False,
    )
