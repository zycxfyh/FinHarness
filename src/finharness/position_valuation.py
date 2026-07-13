"""Typed, evidence-bound valuation checks for capital positions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from finharness.statecore.models import Position
else:
    Position = Any


class ValuationStatus(StrEnum):
    VALUED = "valued"
    VALUED_CONVERTED = "valued_converted"
    UNPRICED = "unpriced"
    FX_MISSING = "fx_missing"
    STALE = "stale"
    UNKNOWN_LEGACY = "unknown_legacy"


ADMITTED_VALUATION_STATUSES = frozenset(
    {ValuationStatus.VALUED.value, ValuationStatus.VALUED_CONVERTED.value}
)


class PositionValuationError(ValueError):
    """Raised when a position cannot support a monetary use case."""


@dataclass(frozen=True)
class ValuationTotals:
    base_currency: str | None
    unified_total: Decimal | None
    per_currency_totals: dict[str, Decimal]
    blockers: tuple[str, ...]

    @property
    def admitted(self) -> bool:
        return not self.blockers and self.unified_total is not None


def valuation_blockers(  # noqa: C901 -- one auditable list of fail-closed evidence checks
    position: Position,
    *,
    evaluated_at: datetime | None = None,
    max_age: timedelta | None = None,
) -> tuple[str, ...]:
    """Return stable blocker codes without deriving missing evidence."""
    blockers: list[str] = []
    status = position.valuation_status
    if status not in ADMITTED_VALUATION_STATUSES:
        blockers.append(f"valuation_{status}")
    required = {
        "market_value": position.market_value,
        "valuation_currency": position.valuation_currency,
        "unit_price": position.unit_price,
        "price_currency": position.price_currency,
        "valued_at_utc": position.valued_at_utc,
        "price_source_ref": position.price_source_ref,
    }
    blockers.extend(f"{name}_missing" for name, value in required.items() if value is None)
    if status == ValuationStatus.VALUED_CONVERTED.value:
        fx_required = {
            "fx_rate": position.fx_rate,
            "fx_as_of_utc": position.fx_as_of_utc,
            "fx_source_ref": position.fx_source_ref,
        }
        blockers.extend(f"{name}_missing" for name, value in fx_required.items() if value is None)
        if position.fx_rate is not None and position.fx_rate <= 0:
            blockers.append("fx_rate_not_positive")
    if (
        position.market_value is not None
        and position.unit_price is not None
        and position.valuation_currency
        and position.price_currency
    ):
        expected = position.quantity * position.unit_price
        if position.price_currency != position.valuation_currency:
            if status != ValuationStatus.VALUED_CONVERTED.value:
                blockers.append("valuation_status_fx_mismatch")
            if position.fx_rate is None:
                blockers.append("fx_rate_missing")
            else:
                expected *= position.fx_rate
        elif status == ValuationStatus.VALUED_CONVERTED.value:
            blockers.append("valuation_status_fx_mismatch")
        if abs(expected - position.market_value) > Decimal("0.01"):
            blockers.append("valuation_components_do_not_reconcile")
    if evaluated_at is not None and max_age is not None and position.valued_at_utc:
        try:
            valued_at = datetime.fromisoformat(position.valued_at_utc.replace("Z", "+00:00"))
        except ValueError:
            blockers.append("valued_at_invalid")
        else:
            if valued_at.utcoffset() is None:
                blockers.append("valued_at_not_timezone_aware")
            elif evaluated_at - valued_at > max_age:
                blockers.append("market_price_stale")
        if status == ValuationStatus.VALUED_CONVERTED.value and position.fx_as_of_utc:
            try:
                fx_as_of = datetime.fromisoformat(position.fx_as_of_utc.replace("Z", "+00:00"))
            except ValueError:
                blockers.append("fx_as_of_invalid")
            else:
                if fx_as_of.utcoffset() is None:
                    blockers.append("fx_as_of_not_timezone_aware")
                elif evaluated_at - fx_as_of > max_age:
                    blockers.append("fx_stale")
    return tuple(dict.fromkeys(blockers))


def reconcile_position_totals(
    positions: Iterable[Position],
    *,
    evaluated_at: datetime | None = None,
    max_age: timedelta | None = None,
) -> ValuationTotals:
    """Aggregate admitted components; never add unlike or unverified currencies."""
    totals: dict[str, Decimal] = {}
    blockers: list[str] = []
    for position in positions:
        row_blockers = valuation_blockers(position, evaluated_at=evaluated_at, max_age=max_age)
        blockers.extend(f"{position.position_id}:{code}" for code in row_blockers)
        if row_blockers or position.market_value is None or not position.valuation_currency:
            continue
        currency = position.valuation_currency
        totals[currency] = totals.get(currency, Decimal("0")) + position.market_value
    if len(totals) > 1:
        blockers.append("mixed_valuation_currencies")
    base_currency = next(iter(totals)) if len(totals) == 1 else None
    unified = totals[base_currency] if base_currency is not None and not blockers else None
    return ValuationTotals(
        base_currency=base_currency,
        unified_total=unified,
        per_currency_totals=totals,
        blockers=tuple(blockers),
    )
