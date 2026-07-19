"""Read-only portfolio snapshot diffs for the state core."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from finharness.position_valuation import reconcile_position_totals
from finharness.statecore.models import ImportBatch, Position, ReceiptManifest, Snapshot
from finharness.statecore.store import StateCoreStoreError

ChangeType = Literal["added", "removed", "changed"]
ChangeReason = Literal["transaction_like", "price_fx", "deletion", "correction"]
PositionKey = tuple[str, str]


@dataclass(frozen=True)
class PositionExposure:
    account_id: str
    instrument_id: str | None
    symbol: str
    quantity: Decimal
    market_value: Decimal | None
    valuation_currency: str | None
    valuation_status: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True)
class PositionChange:
    change_type: ChangeType
    change_reason: ChangeReason
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


@dataclass(frozen=True)
class SnapshotDiff:
    before_snapshot_id: str
    after_snapshot_id: str
    before_as_of_utc: str
    after_as_of_utc: str
    added: tuple[PositionChange, ...]
    removed: tuple[PositionChange, ...]
    changed: tuple[PositionChange, ...]
    total_market_value_before: float | None
    total_market_value_after: float | None
    total_market_value_delta: float | None
    base_currency: str | None
    per_currency_totals_before: dict[str, float]
    per_currency_totals_after: dict[str, float]
    valuation_blockers: tuple[str, ...]
    source_refs: tuple[str, ...]
    corporate_action_gaps: tuple[str, ...]
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
    # Legacy rows retain their historical diff projection, but remain explicitly
    # unresolved and cannot participate in trusted canonical aggregation.
    identity_key = position.instrument_id or f"legacy-symbol:{position.symbol.upper()}"
    return (position.account_id, identity_key)


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
                instrument_id=row.instrument_id,
                symbol=row.symbol.upper(),
                quantity=row.quantity,
                market_value=row.market_value,
                valuation_currency=row.valuation_currency,
                valuation_status=row.valuation_status,
                source_refs=source_refs,
            )
            continue
        exposures[key] = PositionExposure(
            account_id=key[0],
            instrument_id=existing.instrument_id,
            symbol=existing.symbol,
            quantity=existing.quantity + row.quantity,
            market_value=(
                existing.market_value + row.market_value
                if existing.market_value is not None and row.market_value is not None
                else None
            ),
            valuation_currency=(
                existing.valuation_currency
                if existing.valuation_currency == row.valuation_currency
                else None
            ),
            valuation_status=(
                existing.valuation_status
                if existing.valuation_status == row.valuation_status
                else "unknown_legacy"
            ),
            source_refs=tuple(sorted(set(existing.source_refs).union(row.source_refs))),
        )
    return exposures


def _change(
    change_type: ChangeType,
    key: PositionKey,
    before: PositionExposure | None,
    after: PositionExposure | None,
    correction_reason: str | None = None,
) -> PositionChange:
    exposure = after or before
    if exposure is None:  # Defensive: callers always supply one side.
        raise StateCoreStoreError("position change lacks before and after exposure")
    before_quantity = before.quantity if before else Decimal("0")
    after_quantity = after.quantity if after else Decimal("0")
    before_market_value = before.market_value if before else Decimal("0")
    after_market_value = after.market_value if after else Decimal("0")
    source_refs = tuple(
        sorted(set(before.source_refs if before else ()).union(after.source_refs if after else ()))
    )
    if correction_reason is not None:
        change_reason: ChangeReason = "correction"
    elif after is None:
        change_reason = "deletion"
    elif before is None or before.quantity != after.quantity:
        change_reason = "transaction_like"
    else:
        change_reason = "price_fx"
    # Aggregate exactly in Decimal, present the diff as float (JSON/evidence layer).
    return PositionChange(
        change_type=change_type,
        change_reason=change_reason,
        account_id=key[0],
        symbol=exposure.symbol,
        before_quantity=float(before_quantity),
        after_quantity=float(after_quantity),
        quantity_delta=float(after_quantity - before_quantity),
        before_market_value=(
            float(before_market_value) if before_market_value is not None else None
        ),
        after_market_value=(float(after_market_value) if after_market_value is not None else None),
        market_value_delta=(
            float(after_market_value - before_market_value)
            if before_market_value is not None and after_market_value is not None
            else None
        ),
        valuation_currency=exposure.valuation_currency,
        valuation_status=exposure.valuation_status,
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
        before_rows = session.exec(
            select(Position).where(Position.snapshot_id == before_snapshot_id)
        ).all()
        after_rows = session.exec(
            select(Position).where(Position.snapshot_id == after_snapshot_id)
        ).all()
        before_positions = _positions_by_key(session, before_snapshot_id)
        after_positions = _positions_by_key(session, after_snapshot_id)
        after_batch = session.exec(
            select(ImportBatch)
            .join(ReceiptManifest, col(ReceiptManifest.batch_id) == ImportBatch.batch_id)
            .where(ReceiptManifest.snapshot_id == after_snapshot_id)
        ).first()

    before_keys = set(before_positions)
    after_keys = set(after_positions)
    added_keys = after_keys - before_keys
    removed_keys = before_keys - after_keys
    common_keys = before_keys & after_keys

    correction_reason = after_batch.correction_reason if after_batch is not None else None
    added = tuple(
        _change("added", key, None, after_positions[key], correction_reason=correction_reason)
        for key in sorted(added_keys)
    )
    removed = tuple(
        _change("removed", key, before_positions[key], None, correction_reason=correction_reason)
        for key in sorted(removed_keys)
    )
    changed = tuple(
        _change(
            "changed",
            key,
            before_positions[key],
            after_positions[key],
            correction_reason=correction_reason,
        )
        for key in sorted(common_keys)
        if (
            before_positions[key].quantity != after_positions[key].quantity
            or before_positions[key].market_value != after_positions[key].market_value
        )
    )
    before_totals = reconcile_position_totals(
        before_rows,
        evaluated_at=(
            datetime.fromisoformat(before_snapshot.as_of_utc)
            if before_snapshot.as_of_utc else None
        ),
    )
    after_totals = reconcile_position_totals(
        after_rows,
        evaluated_at=(
            datetime.fromisoformat(after_snapshot.as_of_utc)
            if after_snapshot.as_of_utc else None
        ),
    )
    base_currency = (
        before_totals.base_currency
        if before_totals.base_currency == after_totals.base_currency
        else None
    )
    total_before = before_totals.unified_total
    total_after = after_totals.unified_total
    return SnapshotDiff(
        before_snapshot_id=before_snapshot.snapshot_id,
        after_snapshot_id=after_snapshot.snapshot_id,
        before_as_of_utc=before_snapshot.as_of_utc,
        after_as_of_utc=after_snapshot.as_of_utc,
        added=added,
        removed=removed,
        changed=changed,
        total_market_value_before=float(total_before) if total_before is not None else None,
        total_market_value_after=float(total_after) if total_after is not None else None,
        total_market_value_delta=(
            float(total_after - total_before)
            if total_before is not None and total_after is not None and base_currency
            else None
        ),
        base_currency=base_currency,
        per_currency_totals_before={
            key: float(value) for key, value in before_totals.per_currency_totals.items()
        },
        per_currency_totals_after={
            key: float(value) for key, value in after_totals.per_currency_totals.items()
        },
        valuation_blockers=tuple(before_totals.blockers + after_totals.blockers),
        source_refs=tuple(
            sorted(set(before_snapshot.source_refs).union(after_snapshot.source_refs))
        ),
        corporate_action_gaps=(
            tuple(after_batch.corporate_action_gaps) if after_batch is not None else ()
        ),
    )
