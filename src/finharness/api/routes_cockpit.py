"""Read-only cockpit API routes for the B0 product surface."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, func
from sqlmodel import Session, col, select

from finharness.api.dependencies import EngineDependency
from finharness.daily_brief import DailyBrief, compute_daily_brief
from finharness.exposure import ExposureReport, compute_exposure
from finharness.statecore.models import (
    Account,
    Attestation,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    InsurancePolicy,
    Liability,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
    TaxEvent,
    attestation_closes_current_review,
)

router = APIRouter(tags=["cockpit"])

PRODUCT_NON_CLAIMS = (
    "Read-only cockpit summary.",
    "Not investment advice.",
    "Not execution authorization.",
)
BRIEF_KINDS = {"daily_change_brief"}


class DashboardSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    account_count: int
    latest_snapshot_id: str | None
    latest_snapshot_as_of_utc: str | None
    position_count: int
    total_market_value: float
    open_proposal_count: int
    receipt_count: int
    latest_brief_receipt_id: str | None
    liability_count: int
    liability_balance_total: float
    goal_count: int
    cashflow_count: int
    tax_event_count: int
    insurance_policy_count: int
    document_count: int
    source_refs: tuple[str, ...]
    non_claims: tuple[str, ...] = PRODUCT_NON_CLAIMS
    execution_allowed: bool = False


class BriefLatestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    available: bool
    receipt: ReceiptIndex | None
    source_refs: tuple[str, ...]
    non_claims: tuple[str, ...] = PRODUCT_NON_CLAIMS
    execution_allowed: bool = False


class TimelineEntry(BaseModel):
    event_type: str
    object_id: str
    created_at_utc: str
    summary: str
    source_refs: tuple[str, ...]
    execution_allowed: bool = False


class ControlsStatusResponse(BaseModel):
    api_execution_endpoints_present: bool = True
    proposal_approval_is_execution_authorization: bool = False
    execution_allowed: bool = False
    safeguards: tuple[str, ...]
    limitations: tuple[str, ...]
    non_claims: tuple[str, ...] = PRODUCT_NON_CLAIMS


class ControlsLimitsResponse(BaseModel):
    raising_limits_via_api_allowed: bool = False
    execution_allowed: bool = False
    configured_limits: tuple[dict[str, str], ...] = ()
    limitations: tuple[str, ...]
    non_claims: tuple[str, ...] = PRODUCT_NON_CLAIMS


def _latest_portfolio_snapshot(session: Session) -> Snapshot | None:
    return session.exec(
        select(Snapshot)
        .where(Snapshot.kind == "portfolio")
        .order_by(desc(Snapshot.as_of_utc), desc(Snapshot.snapshot_id))
        .limit(1)
    ).first()


def _latest_brief_receipt(session: Session) -> ReceiptIndex | None:
    return session.exec(
        select(ReceiptIndex)
        .where(col(ReceiptIndex.kind).in_(BRIEF_KINDS))
        .order_by(desc(ReceiptIndex.created_at_utc), desc(ReceiptIndex.receipt_id))
        .limit(1)
    ).first()


def _open_proposal_count(
    proposals: list[Proposal],
    attestations: list[Attestation],
) -> int:
    proposals_by_id = {proposal.proposal_id: proposal for proposal in proposals}
    attested_ids = {
        attestation.proposal_id
        for attestation in attestations
        if (proposal := proposals_by_id.get(attestation.proposal_id)) is not None
        and attestation_closes_current_review(attestation, proposal)
    }
    return sum(1 for proposal in proposals if proposal.proposal_id not in attested_ids)


@router.get("/exposure", response_model=ExposureReport)
async def exposure(engine: EngineDependency) -> ExposureReport:
    """Read-only personal exposure map (net worth, concentration, runway, obligations)."""
    return compute_exposure(engine)


@router.get("/brief/daily", response_model=DailyBrief)
async def daily_brief(engine: EngineDependency) -> DailyBrief:
    """Read-only unified daily brief (exposure + change + obligations + reviews)."""
    return compute_daily_brief(engine)


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(engine: EngineDependency) -> DashboardSummaryResponse:
    with Session(engine) as session:
        accounts = list(session.exec(select(Account)).all())
        proposals = list(session.exec(select(Proposal)).all())
        attestations = list(session.exec(select(Attestation)).all())
        receipt_count = session.scalar(select(func.count()).select_from(ReceiptIndex)) or 0
        latest_brief = _latest_brief_receipt(session)
        liabilities = list(session.exec(select(Liability)).all())
        goals = list(session.exec(select(FinancialGoal)).all())
        cashflows = list(session.exec(select(CashflowEvent)).all())
        tax_events = list(session.exec(select(TaxEvent)).all())
        insurance_policies = list(session.exec(select(InsurancePolicy)).all())
        documents = list(session.exec(select(DocumentRef)).all())
        latest_snapshot = _latest_portfolio_snapshot(session)
        positions: list[Position] = []
        if latest_snapshot is not None:
            positions = list(
                session.exec(
                    select(Position).where(Position.snapshot_id == latest_snapshot.snapshot_id)
                ).all()
            )

    source_refs = tuple(sorted(set(latest_snapshot.source_refs if latest_snapshot else ())))
    return DashboardSummaryResponse(
        account_count=len(accounts),
        latest_snapshot_id=latest_snapshot.snapshot_id if latest_snapshot else None,
        latest_snapshot_as_of_utc=latest_snapshot.as_of_utc if latest_snapshot else None,
        position_count=len(positions),
        total_market_value=float(
            sum((position.market_value for position in positions), Decimal("0"))
        ),
        open_proposal_count=_open_proposal_count(proposals, attestations),
        receipt_count=receipt_count,
        latest_brief_receipt_id=latest_brief.receipt_id if latest_brief else None,
        liability_count=len(liabilities),
        # Sum exactly in Decimal, then expose a float display rollup (the raw
        # /state/liabilities rows keep the exact Decimal balance).
        liability_balance_total=float(
            sum((liability.balance for liability in liabilities), Decimal("0"))
        ),
        goal_count=len(goals),
        cashflow_count=len(cashflows),
        tax_event_count=len(tax_events),
        insurance_policy_count=len(insurance_policies),
        document_count=len(documents),
        source_refs=source_refs,
    )


@router.get("/brief/latest", response_model=BriefLatestResponse)
async def latest_brief(engine: EngineDependency) -> BriefLatestResponse:
    with Session(engine) as session:
        receipt = _latest_brief_receipt(session)
    return BriefLatestResponse(
        available=receipt is not None,
        receipt=receipt,
        source_refs=tuple(receipt.source_refs if receipt else ()),
    )


@router.get("/receipts", response_model=list[ReceiptIndex])
async def list_receipts(
    engine: EngineDependency,
    kind: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ReceiptIndex]:
    statement = select(ReceiptIndex).order_by(
        desc(ReceiptIndex.created_at_utc),
        desc(ReceiptIndex.receipt_id),
    )
    if kind is not None:
        statement = statement.where(ReceiptIndex.kind == kind)
    with Session(engine) as session:
        return list(session.exec(statement.limit(limit)).all())


@router.get("/timeline", response_model=list[TimelineEntry])
async def timeline(
    engine: EngineDependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[TimelineEntry]:
    entries: list[TimelineEntry] = []
    # Each source contributes at most `limit` rows, ordered newest-first in SQL,
    # so the merged top-`limit` is correct without loading whole tables.
    with Session(engine) as session:
        snapshots = list(
            session.exec(
                select(Snapshot)
                .order_by(desc(Snapshot.as_of_utc), desc(Snapshot.snapshot_id))
                .limit(limit)
            ).all()
        )
        proposals = list(
            session.exec(
                select(Proposal)
                .order_by(desc(Proposal.created_at_utc), desc(Proposal.proposal_id))
                .limit(limit)
            ).all()
        )
        attestations = list(
            session.exec(
                select(Attestation)
                .order_by(desc(Attestation.created_at_utc), desc(Attestation.attestation_id))
                .limit(limit)
            ).all()
        )
        receipts = list(
            session.exec(
                select(ReceiptIndex)
                .order_by(desc(ReceiptIndex.created_at_utc), desc(ReceiptIndex.receipt_id))
                .limit(limit)
            ).all()
        )

    for snapshot in snapshots:
        entries.append(
            TimelineEntry(
                event_type="snapshot",
                object_id=snapshot.snapshot_id,
                created_at_utc=snapshot.as_of_utc,
                summary=f"{snapshot.kind} snapshot recorded",
                source_refs=tuple(snapshot.source_refs),
            )
        )
    for proposal in proposals:
        entries.append(
            TimelineEntry(
                event_type="proposal",
                object_id=proposal.proposal_id,
                created_at_utc=proposal.created_at_utc,
                summary=proposal.claim,
                source_refs=tuple(proposal.source_refs),
            )
        )
    for attestation in attestations:
        entries.append(
            TimelineEntry(
                event_type="attestation",
                object_id=attestation.attestation_id,
                created_at_utc=attestation.created_at_utc,
                summary=f"{attestation.decision} by {attestation.attester}",
                source_refs=tuple(attestation.source_refs),
            )
        )
    for receipt in receipts:
        entries.append(
            TimelineEntry(
                event_type=f"receipt:{receipt.kind}",
                object_id=receipt.receipt_id,
                created_at_utc=receipt.created_at_utc,
                summary=f"Receipt indexed: {receipt.path}",
                source_refs=tuple(receipt.source_refs),
            )
        )

    return sorted(
        entries,
        key=lambda entry: (entry.created_at_utc, entry.object_id),
        reverse=True,
    )[:limit]


class ExecutionControlsStatusResponse(ControlsStatusResponse):
    execution_substrate: str = "simulated"
    live_execution_available: bool = False


@router.get("/controls/status", response_model=ExecutionControlsStatusResponse)
async def controls_status() -> ExecutionControlsStatusResponse:
    return ExecutionControlsStatusResponse(
        safeguards=(
            "Ordinary Cockpit navigation does not expose the simulated execution preview.",
            "Proposal approval is recorded as human attestation, not execution authorization.",
            "The only registered broker adapter is simulated; live execution is unavailable.",
        ),
        limitations=(
            "This endpoint summarizes product-surface controls only.",
            "It is not a compliance certification or release approval.",
        ),
    )


@router.get("/controls/limits", response_model=ControlsLimitsResponse)
async def controls_limits() -> ControlsLimitsResponse:
    return ControlsLimitsResponse(
        limitations=(
            "No product API endpoint can raise configured ceilings.",
            "Configured trading ceilings remain governed by effective ceiling "
            "and rule-change modules.",
            "No first-class ControlLimit state table is exposed in this P0 cockpit slice.",
        ),
    )
