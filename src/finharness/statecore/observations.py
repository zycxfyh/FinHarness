"""Deterministic portfolio-change observations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any, Literal

from finharness.statecore.diff import PositionChange, SnapshotDiff
from finharness.statecore.models import Position

ObservationKind = Literal[
    "new_position",
    "closed_position",
    "material_move",
    "total_exposure_delta",
    "concentration",
    "data_gap",
]


@dataclass(frozen=True)
class Observation:
    kind: ObservationKind
    detail: str
    numbers: dict[str, Any]
    threshold: dict[str, float]
    crossed: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ObservationThresholds:
    min_position_market_value: float = 25.0
    quantity_change_pct: float = 0.25
    market_value_change_pct: float = 0.25
    total_exposure_change_pct: float = 0.20
    concentration_pct: float = 0.40
    cash_runway_target_months: float = 6.0
    cash_overweight_pct: float = 0.50
    high_interest_rate_pct: float = 0.10
    data_gap_min_market_value: float = 1.0

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def _ratio(delta: float, base: float) -> float | None:
    if base == 0:
        return None
    return delta / abs(base)


def _abs_ratio(delta: float, base: float) -> float | None:
    ratio = _ratio(delta, base)
    return abs(ratio) if ratio is not None else None


def _new_position(change: PositionChange, thresholds: ObservationThresholds) -> Observation | None:
    if abs(change.after_market_value) < thresholds.min_position_market_value:
        return None
    return Observation(
        kind="new_position",
        detail=(
            f"{change.symbol} appears in the after snapshot with market_value "
            f"{change.after_market_value:.2f}."
        ),
        numbers={
            "account_id": change.account_id,
            "symbol": change.symbol,
            "after_quantity": change.after_quantity,
            "after_market_value": change.after_market_value,
        },
        threshold={"min_position_market_value": thresholds.min_position_market_value},
        crossed=True,
    )


def _closed_position(
    change: PositionChange,
    thresholds: ObservationThresholds,
) -> Observation | None:
    if abs(change.before_market_value) < thresholds.min_position_market_value:
        return None
    return Observation(
        kind="closed_position",
        detail=(
            f"{change.symbol} no longer appears in the after snapshot; prior "
            f"market_value was {change.before_market_value:.2f}."
        ),
        numbers={
            "account_id": change.account_id,
            "symbol": change.symbol,
            "before_quantity": change.before_quantity,
            "before_market_value": change.before_market_value,
        },
        threshold={"min_position_market_value": thresholds.min_position_market_value},
        crossed=True,
    )


def _material_move(change: PositionChange, thresholds: ObservationThresholds) -> Observation | None:
    quantity_change_pct = _abs_ratio(change.quantity_delta, change.before_quantity)
    market_value_change_pct = _abs_ratio(
        change.market_value_delta,
        change.before_market_value,
    )
    quantity_crossed = (
        quantity_change_pct is not None and quantity_change_pct >= thresholds.quantity_change_pct
    )
    market_value_crossed = (
        market_value_change_pct is not None
        and market_value_change_pct >= thresholds.market_value_change_pct
    )
    if not quantity_crossed and not market_value_crossed:
        return None
    return Observation(
        kind="material_move",
        detail=(
            f"{change.symbol} changed by quantity_delta {change.quantity_delta:.4f} "
            f"and market_value_delta {change.market_value_delta:.2f}."
        ),
        numbers={
            "account_id": change.account_id,
            "symbol": change.symbol,
            "before_quantity": change.before_quantity,
            "after_quantity": change.after_quantity,
            "quantity_delta": change.quantity_delta,
            "quantity_change_pct": quantity_change_pct,
            "before_market_value": change.before_market_value,
            "after_market_value": change.after_market_value,
            "market_value_delta": change.market_value_delta,
            "market_value_change_pct": market_value_change_pct,
        },
        threshold={
            "quantity_change_pct": thresholds.quantity_change_pct,
            "market_value_change_pct": thresholds.market_value_change_pct,
        },
        crossed=True,
    )


def _total_exposure_delta(
    diff: SnapshotDiff,
    thresholds: ObservationThresholds,
) -> Observation | None:
    change_pct = _abs_ratio(
        diff.total_market_value_delta,
        diff.total_market_value_before,
    )
    if change_pct is None or change_pct < thresholds.total_exposure_change_pct:
        return None
    return Observation(
        kind="total_exposure_delta",
        detail=(f"Total market value changed by {diff.total_market_value_delta:.2f}."),
        numbers={
            "total_market_value_before": diff.total_market_value_before,
            "total_market_value_after": diff.total_market_value_after,
            "total_market_value_delta": diff.total_market_value_delta,
            "total_exposure_change_pct": change_pct,
        },
        threshold={"total_exposure_change_pct": thresholds.total_exposure_change_pct},
        crossed=True,
    )


def _position_totals_by_identity(
    positions: Sequence[Position],
) -> dict[str, tuple[str, Decimal]]:
    totals: dict[str, tuple[str, Decimal]] = {}
    for position in positions:
        identity_key = position.instrument_id or f"unresolved:{position.position_id}"
        symbol = position.symbol.upper()
        prior = totals.get(identity_key, (symbol, Decimal("0")))[1]
        totals[identity_key] = (symbol, prior + position.market_value)
    return totals


def _concentration_observations(
    positions: Sequence[Position],
    thresholds: ObservationThresholds,
) -> list[Observation]:
    totals = _position_totals_by_identity(positions)
    total_market_value = sum((item[1] for item in totals.values()), Decimal("0"))
    if total_market_value <= 0:
        return []
    observations: list[Observation] = []
    for instrument_id, (symbol, market_value) in sorted(totals.items()):
        concentration_pct = float(market_value / total_market_value)
        if concentration_pct < thresholds.concentration_pct:
            continue
        observations.append(
            Observation(
                kind="concentration",
                detail=(f"{symbol} is {concentration_pct:.2%} of total market value."),
                numbers={
                    "symbol": symbol,
                    "instrument_id": (
                        None if instrument_id.startswith("unresolved:") else instrument_id
                    ),
                    "symbol_market_value": float(market_value),
                    "total_market_value": float(total_market_value),
                    "concentration_pct": concentration_pct,
                },
                threshold={"concentration_pct": thresholds.concentration_pct},
                crossed=True,
            )
        )
    return observations


def _data_gap_observations(
    positions: Sequence[Position],
    thresholds: ObservationThresholds,
) -> list[Observation]:
    observations: list[Observation] = []
    ordered_positions = sorted(
        positions,
        key=lambda item: (item.account_id, item.symbol, item.position_id),
    )
    for position in ordered_positions:
        if position.cost_basis is not None:
            continue
        if abs(position.market_value) < thresholds.data_gap_min_market_value:
            continue
        observations.append(
            Observation(
                kind="data_gap",
                detail=(f"{position.symbol} cost_basis is not disclosed in the source snapshot."),
                numbers={
                    "account_id": position.account_id,
                    "symbol": position.symbol.upper(),
                    "market_value": float(position.market_value),
                    "cost_basis_disclosed": False,
                },
                threshold={"data_gap_min_market_value": thresholds.data_gap_min_market_value},
                crossed=True,
            )
        )
    return observations


def build_observations(
    diff: SnapshotDiff,
    current_positions: Sequence[Position],
    *,
    thresholds: ObservationThresholds | None = None,
) -> tuple[Observation, ...]:
    """Build deterministic, descriptive observations from state diff data."""
    active_thresholds = thresholds or ObservationThresholds()
    observations: list[Observation] = []
    observations.extend(
        observation
        for change in diff.added
        if (observation := _new_position(change, active_thresholds)) is not None
    )
    observations.extend(
        observation
        for change in diff.removed
        if (observation := _closed_position(change, active_thresholds)) is not None
    )
    observations.extend(
        observation
        for change in diff.changed
        if (observation := _material_move(change, active_thresholds)) is not None
    )
    total_observation = _total_exposure_delta(diff, active_thresholds)
    if total_observation is not None:
        observations.append(total_observation)
    observations.extend(_concentration_observations(current_positions, active_thresholds))
    observations.extend(_data_gap_observations(current_positions, active_thresholds))
    return tuple(observations)
