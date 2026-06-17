"""Read-only state API routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, select

from finharness.api.dependencies import EngineDependency
from finharness.statecore.diff import diff_snapshots
from finharness.statecore.models import Account, Position, ReceiptIndex, Snapshot
from finharness.statecore.store import StateCoreStoreError

router = APIRouter(tags=["state"])


class PositionChangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    change_type: str
    account_id: str
    symbol: str
    before_quantity: float
    after_quantity: float
    quantity_delta: float
    before_market_value: float
    after_market_value: float
    market_value_delta: float
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
    total_market_value_before: float
    total_market_value_after: float
    total_market_value_delta: float
    source_refs: tuple[str, ...]
    non_claims: tuple[str, ...]
    execution_allowed: bool


@router.get("/state/accounts", response_model=list[Account])
def list_accounts(engine: EngineDependency) -> list[Account]:
    with Session(engine) as session:
        return list(
            session.exec(select(Account).order_by(Account.account_id)).all()
        )


@router.get("/state/positions", response_model=list[Position])
def list_positions(
    engine: EngineDependency,
    snapshot_id: Annotated[str | None, Query()] = None,
) -> list[Position]:
    statement = select(Position).order_by(Position.account_id, Position.symbol)
    if snapshot_id is not None:
        statement = statement.where(Position.snapshot_id == snapshot_id)
    with Session(engine) as session:
        return list(session.exec(statement).all())


@router.get("/snapshots", response_model=list[Snapshot])
def list_snapshots(
    engine: EngineDependency,
    kind: Annotated[str | None, Query()] = None,
) -> list[Snapshot]:
    statement = select(Snapshot).order_by(Snapshot.as_of_utc, Snapshot.snapshot_id)
    if kind is not None:
        statement = statement.where(Snapshot.kind == kind)
    with Session(engine) as session:
        return list(session.exec(statement).all())


@router.get("/diff", response_model=SnapshotDiffResponse)
def get_diff(
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
def get_receipt(receipt_id: str, engine: EngineDependency) -> ReceiptIndex:
    with Session(engine) as session:
        receipt = session.get(ReceiptIndex, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail=f"receipt not found: {receipt_id}")
    return receipt
