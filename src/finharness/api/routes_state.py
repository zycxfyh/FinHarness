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


def _list_all[ModelT: SQLModel](
    engine: Engine, model: type[ModelT], *order_by: Any
) -> list[ModelT]:
    """Return every row of a read-only state table in a stable order."""
    with Session(engine) as session:
        return list(session.exec(select(model).order_by(*order_by)).all())


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
async def list_accounts(engine: EngineDependency) -> list[Account]:
    return _list_all(engine, Account, Account.account_id)


@router.get("/state/positions", response_model=list[Position])
async def list_positions(
    engine: EngineDependency,
    snapshot_id: Annotated[str | None, Query()] = None,
) -> list[Position]:
    statement = select(Position).order_by(Position.account_id, Position.symbol)
    if snapshot_id is not None:
        statement = statement.where(Position.snapshot_id == snapshot_id)
    with Session(engine) as session:
        return list(session.exec(statement).all())


@router.get("/state/liabilities", response_model=list[Liability])
async def list_liabilities(engine: EngineDependency) -> list[Liability]:
    return _list_all(engine, Liability, Liability.name)


@router.get("/state/goals", response_model=list[FinancialGoal])
async def list_goals(engine: EngineDependency) -> list[FinancialGoal]:
    return _list_all(engine, FinancialGoal, FinancialGoal.name)


@router.get("/state/cashflows", response_model=list[CashflowEvent])
async def list_cashflows(engine: EngineDependency) -> list[CashflowEvent]:
    return _list_all(engine, CashflowEvent, CashflowEvent.event_date, CashflowEvent.cashflow_id)


@router.get("/state/tax-events", response_model=list[TaxEvent])
async def list_tax_events(engine: EngineDependency) -> list[TaxEvent]:
    return _list_all(engine, TaxEvent, TaxEvent.due_date, TaxEvent.tax_event_id)


@router.get("/state/insurance", response_model=list[InsurancePolicy])
async def list_insurance(engine: EngineDependency) -> list[InsurancePolicy]:
    return _list_all(engine, InsurancePolicy, InsurancePolicy.policy_id)


@router.get("/state/documents", response_model=list[DocumentRef])
async def list_documents(engine: EngineDependency) -> list[DocumentRef]:
    return _list_all(engine, DocumentRef, DocumentRef.document_id)


@router.get("/snapshots", response_model=list[Snapshot])
async def list_snapshots(
    engine: EngineDependency,
    kind: Annotated[str | None, Query()] = None,
) -> list[Snapshot]:
    statement = select(Snapshot).order_by(Snapshot.as_of_utc, Snapshot.snapshot_id)
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
