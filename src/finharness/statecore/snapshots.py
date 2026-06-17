"""Read-only portfolio snapshot queries."""

from __future__ import annotations

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.statecore.models import Position, Snapshot


def latest_portfolio_snapshot(
    *,
    engine: Engine,
    before: str | None = None,
) -> Snapshot | None:
    """Return the latest portfolio snapshot before the optional as-of timestamp."""
    statement = select(Snapshot).where(Snapshot.kind == "portfolio")
    if before is not None:
        statement = statement.where(Snapshot.as_of_utc < before)
    statement = statement.order_by(Snapshot.as_of_utc.desc(), Snapshot.snapshot_id.desc())
    with Session(engine) as session:
        return session.exec(statement).first()


def portfolio_positions(
    snapshot_id: str,
    *,
    engine: Engine,
) -> list[Position]:
    """Return positions for a portfolio snapshot in deterministic order."""
    statement = (
        select(Position)
        .where(Position.snapshot_id == snapshot_id)
        .order_by(Position.account_id, Position.symbol, Position.position_id)
    )
    with Session(engine) as session:
        return list(session.exec(statement).all())
