"""Read-only portfolio snapshot diffs for the state core."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.statecore.models import Position, Snapshot
from finharness.statecore.store import StateCoreStoreError

ChangeType = Literal["added", "removed", "changed"]
PositionKey = tuple[str, str]


@dataclass(frozen=True)
class PositionExposure:
    account_id: str
    symbol: str
    quantity: float
    market_value: float
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class PositionChange:
    change_type: ChangeType
    account_id: str
    symbol: str
    before_quantity: float
    after_quantity: float
    quantity_delta: float
    before_market_value: float
    after_market_value: float
    market_value_delta: float
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class SnapshotDiff:
    before_snapshot_id: str
    after_snapshot_id: str
    before_as_of_utc: str
    after_as_of_utc: str
    added: tuple[PositionChange, ...]
    removed: tuple[PositionChange, ...]
    changed: tuple[PositionChange, ...]
    total_market_value_before: float
    total_market_value_after: float
    total_market_value_delta: float
    source_refs: tuple[str, ...]
    non_claims: tuple[str, ...] = (
        "Descriptive state diff only.",
        "Not investment advice.",
        "Not trading authorization.",
    )
    execution_allowed: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _snapshot_or_raise(session: Session, snapshot_id: str) -> Snapshot:
    snapshot = session.get(Snapshot, snapshot_id)
    if snapshot is None:
        raise StateCoreStoreError(f"snapshot not found: {snapshot_id}")
    if snapshot.kind != "portfolio":
        raise StateCoreStoreError(f"snapshot is not a portfolio snapshot: {snapshot_id}")
    return snapshot


def _position_key(position: Position) -> PositionKey:
    return (position.account_id, position.symbol.upper())


def _positions_by_key(session: Session, snapshot_id: str) -> dict[PositionKey, PositionExposure]:
    rows = session.exec(select(Position).where(Position.snapshot_id == snapshot_id)).all()
    exposures: dict[PositionKey, PositionExposure] = {}
    for row in rows:
        key = _position_key(row)
        existing = exposures.get(key)
        source_refs = tuple(sorted(set(row.source_refs)))
        if existing is None:
            exposures[key] = PositionExposure(
                account_id=key[0],
                symbol=key[1],
                quantity=row.quantity,
                market_value=row.market_value,
                source_refs=source_refs,
            )
            continue
        exposures[key] = PositionExposure(
            account_id=key[0],
            symbol=key[1],
            quantity=existing.quantity + row.quantity,
            market_value=existing.market_value + row.market_value,
            source_refs=tuple(sorted(set(existing.source_refs).union(row.source_refs))),
        )
    return exposures


def _change(
    change_type: ChangeType,
    key: PositionKey,
    before: PositionExposure | None,
    after: PositionExposure | None,
) -> PositionChange:
    before_quantity = before.quantity if before else 0.0
    after_quantity = after.quantity if after else 0.0
    before_market_value = before.market_value if before else 0.0
    after_market_value = after.market_value if after else 0.0
    source_refs = tuple(
        sorted(
            set(before.source_refs if before else ()).union(
                after.source_refs if after else ()
            )
        )
    )
    return PositionChange(
        change_type=change_type,
        account_id=key[0],
        symbol=key[1],
        before_quantity=before_quantity,
        after_quantity=after_quantity,
        quantity_delta=after_quantity - before_quantity,
        before_market_value=before_market_value,
        after_market_value=after_market_value,
        market_value_delta=after_market_value - before_market_value,
        source_refs=source_refs,
    )


def diff_snapshots(
    before_snapshot_id: str,
    after_snapshot_id: str,
    *,
    engine: Engine,
) -> SnapshotDiff:
    """Return a descriptive diff between two portfolio snapshots.

    This is a pure query helper. It does not write proposals, receipts, orders,
    approvals, or any other decision artifact.
    """
    with Session(engine) as session:
        before_snapshot = _snapshot_or_raise(session, before_snapshot_id)
        after_snapshot = _snapshot_or_raise(session, after_snapshot_id)
        before_positions = _positions_by_key(session, before_snapshot_id)
        after_positions = _positions_by_key(session, after_snapshot_id)

    before_keys = set(before_positions)
    after_keys = set(after_positions)
    added_keys = after_keys - before_keys
    removed_keys = before_keys - after_keys
    common_keys = before_keys & after_keys

    added = tuple(
        _change("added", key, None, after_positions[key])
        for key in sorted(added_keys)
    )
    removed = tuple(
        _change("removed", key, before_positions[key], None)
        for key in sorted(removed_keys)
    )
    changed = tuple(
        _change("changed", key, before_positions[key], after_positions[key])
        for key in sorted(common_keys)
        if (
            before_positions[key].quantity != after_positions[key].quantity
            or before_positions[key].market_value != after_positions[key].market_value
        )
    )
    total_before = sum(position.market_value for position in before_positions.values())
    total_after = sum(position.market_value for position in after_positions.values())
    return SnapshotDiff(
        before_snapshot_id=before_snapshot.snapshot_id,
        after_snapshot_id=after_snapshot.snapshot_id,
        before_as_of_utc=before_snapshot.as_of_utc,
        after_as_of_utc=after_snapshot.as_of_utc,
        added=added,
        removed=removed,
        changed=changed,
        total_market_value_before=total_before,
        total_market_value_after=total_after,
        total_market_value_delta=total_after - total_before,
        source_refs=tuple(
            sorted(set(before_snapshot.source_refs).union(after_snapshot.source_refs))
        ),
    )
