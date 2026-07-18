"""Read-only state API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, select

from finharness.api.dependencies import EngineDependency
from finharness.statecore.diff import diff_snapshots
from finharness.statecore.models import (
    Account,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    InsurancePolicy,
    Liability,
    Position,
    ReceiptIndex,
    Snapshot,
    TaxEvent,
)
from finharness.statecore.store import StateCoreStoreError

router = APIRouter(tags=["state"])

DEFAULT_COLLECTION_LIMIT = 100
MAX_COLLECTION_LIMIT = 200
CollectionLimit = Annotated[
    int,
    Query(
        ge=1,
        le=MAX_COLLECTION_LIMIT,
        description="Maximum rows returned; defaults to 100 and cannot exceed 200.",
    ),
]
CollectionOffset = Annotated[
    int,
    Query(
        ge=0,
        description="Rows skipped in the endpoint's documented stable order.",
    ),
]


def _list_page[ModelT: SQLModel](
    engine: Engine,
    model: type[ModelT],
    *order_by: Any,
    limit: int,
    offset: int,
) -> list[ModelT]:
    """Return a bounded page of a read-only state table in a stable order."""
    with Session(engine) as session:
        statement = select(model).order_by(*order_by).offset(offset).limit(limit)
        return list(session.exec(statement).all())


class PositionChangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    change_type: str
    change_reason: str
    account_id: str
    symbol: str
    before_quantity: float
    after_quantity: float
    quantity_delta: float
    before_market_value: float | None
    after_market_value: float | None
    market_value_delta: float | None
    valuation_currency: str | None
    valuation_status: str
    source_refs: tuple[str, ...]


class SnapshotDiffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    before_snapshot_id: str
    after_snapshot_id: str
    before_as_of_utc: str
    after_as_of_utc: str
    added: tuple[PositionChangeResponse, ...]
    removed: tuple[PositionChangeResponse, ...]
    changed: tuple[PositionChangeResponse, ...]
    total_market_value_before: float | None
    total_market_value_after: float | None
    total_market_value_delta: float | None
    base_currency: str | None
    per_currency_totals_before: dict[str, float]
    per_currency_totals_after: dict[str, float]
    valuation_blockers: tuple[str, ...]
    source_refs: tuple[str, ...]
    corporate_action_gaps: tuple[str, ...]
    non_claims: tuple[str, ...]
    execution_allowed: bool


@router.get("/state/accounts", response_model=list[Account])
async def list_accounts(
    engine: EngineDependency,
    limit: CollectionLimit = DEFAULT_COLLECTION_LIMIT,
    offset: CollectionOffset = 0,
) -> list[Account]:
    return _list_page(engine, Account, Account.account_id, limit=limit, offset=offset)


@router.get("/state/positions", response_model=list[Position])
async def list_positions(
    engine: EngineDependency,
    snapshot_id: Annotated[
        str,
        Query(
            min_length=1,
            description="Required snapshot scope; unscoped historical position reads are rejected.",
        ),
    ],
    limit: CollectionLimit = DEFAULT_COLLECTION_LIMIT,
    offset: CollectionOffset = 0,
) -> list[Position]:
    statement = (
        select(Position)
        .where(Position.snapshot_id == snapshot_id)
        .order_by(Position.account_id, Position.symbol, Position.position_id)
        .offset(offset)
        .limit(limit)
    )
    with Session(engine) as session:
        if session.get(Snapshot, snapshot_id) is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "snapshot_not_found",
                    "message": f"snapshot not found: {snapshot_id}",
                    "snapshot_id": snapshot_id,
                },
            )
        return list(session.exec(statement).all())


@router.get("/state/liabilities", response_model=list[Liability])
async def list_liabilities(
    engine: EngineDependency,
    limit: CollectionLimit = DEFAULT_COLLECTION_LIMIT,
    offset: CollectionOffset = 0,
) -> list[Liability]:
    return _list_page(
        engine, Liability, Liability.name, Liability.liability_id, limit=limit, offset=offset
    )


@router.get("/state/goals", response_model=list[FinancialGoal])
async def list_goals(
    engine: EngineDependency,
    limit: CollectionLimit = DEFAULT_COLLECTION_LIMIT,
    offset: CollectionOffset = 0,
) -> list[FinancialGoal]:
    return _list_page(
        engine, FinancialGoal, FinancialGoal.name, FinancialGoal.goal_id, limit=limit, offset=offset
    )


@router.get("/state/cashflows", response_model=list[CashflowEvent])
async def list_cashflows(
    engine: EngineDependency,
    limit: CollectionLimit = DEFAULT_COLLECTION_LIMIT,
    offset: CollectionOffset = 0,
) -> list[CashflowEvent]:
    return _list_page(
        engine,
        CashflowEvent,
        CashflowEvent.event_date,
        CashflowEvent.cashflow_id,
        limit=limit,
        offset=offset,
    )


@router.get("/state/tax-events", response_model=list[TaxEvent])
async def list_tax_events(
    engine: EngineDependency,
    limit: CollectionLimit = DEFAULT_COLLECTION_LIMIT,
    offset: CollectionOffset = 0,
) -> list[TaxEvent]:
    return _list_page(
        engine,
        TaxEvent,
        TaxEvent.due_date,
        TaxEvent.tax_event_id,
        limit=limit,
        offset=offset,
    )


@router.get("/state/insurance", response_model=list[InsurancePolicy])
async def list_insurance(
    engine: EngineDependency,
    limit: CollectionLimit = DEFAULT_COLLECTION_LIMIT,
    offset: CollectionOffset = 0,
) -> list[InsurancePolicy]:
    return _list_page(
        engine, InsurancePolicy, InsurancePolicy.policy_id, limit=limit, offset=offset
    )


@router.get("/state/documents", response_model=list[DocumentRef])
async def list_documents(
    engine: EngineDependency,
    limit: CollectionLimit = DEFAULT_COLLECTION_LIMIT,
    offset: CollectionOffset = 0,
) -> list[DocumentRef]:
    return _list_page(engine, DocumentRef, DocumentRef.document_id, limit=limit, offset=offset)


@router.get("/snapshots", response_model=list[Snapshot])
async def list_snapshots(
    engine: EngineDependency,
    kind: Annotated[str | None, Query()] = None,
    limit: CollectionLimit = DEFAULT_COLLECTION_LIMIT,
    offset: CollectionOffset = 0,
) -> list[Snapshot]:
    statement = (
        select(Snapshot)
        .order_by(Snapshot.as_of_utc, Snapshot.snapshot_id)
        .offset(offset)
        .limit(limit)
    )
    if kind is not None:
        statement = statement.where(Snapshot.kind == kind)
    with Session(engine) as session:
        return list(session.exec(statement).all())


@router.get("/diff", response_model=SnapshotDiffResponse)
async def get_diff(
    engine: EngineDependency,
    before_snapshot_id: Annotated[str, Query()],
    after_snapshot_id: Annotated[str, Query()],
) -> SnapshotDiffResponse:
    try:
        diff = diff_snapshots(
            before_snapshot_id,
            after_snapshot_id,
            engine=engine,
        )
    except StateCoreStoreError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc
    return SnapshotDiffResponse.model_validate(diff)


@router.get("/receipts/{receipt_id}", response_model=ReceiptIndex)
async def get_receipt(receipt_id: str, engine: EngineDependency) -> ReceiptIndex:
    with Session(engine) as session:
        receipt = session.get(ReceiptIndex, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"receipt not found: {receipt_id}")
    return receipt
