"""Paper TCA and cost-estimate helpers."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from finharness.execution import ExecutionEvent, ExecutionOrderRequest, ExecutionSnapshot
from finharness.post_trade.models import (
    PostTradeContext,
    PostTradeCostEstimate,
    PostTradeReconciliation,
)
from finharness.post_trade.reconciliation import events_by_order


def average_fill_price(events: list[ExecutionEvent]) -> float | None:
    prices = [
        item.average_price
        for item in events
        if item.filled_quantity > 0 and item.average_price is not None
    ]
    if not prices:
        return None
    return sum(prices) / len(prices)


def implementation_shortfall(
    *,
    side: Literal["buy", "sell"] | None,
    arrival_price: float | None,
    execution_price: float | None,
    filled_quantity: int,
) -> float | None:
    if side is None or arrival_price is None or execution_price is None:
        return None
    if filled_quantity <= 0:
        return None
    if side == "buy":
        return (execution_price - arrival_price) * filled_quantity
    return (arrival_price - execution_price) * filled_quantity


def build_cost_estimates(
    *,
    execution_snapshot: ExecutionSnapshot,
    context: PostTradeContext,
    reconciliations: list[PostTradeReconciliation],
) -> list[PostTradeCostEstimate]:
    grouped = events_by_order(execution_snapshot)
    requests_by_id: dict[str, ExecutionOrderRequest] = {
        request.order_request_id: request for request in execution_snapshot.order_requests
    }
    estimates: list[PostTradeCostEstimate] = []
    for reconciliation in reconciliations:
        request = (
            requests_by_id.get(reconciliation.order_request_id)
            if reconciliation.order_request_id
            else None
        )
        events = grouped.get(reconciliation.order_request_id, [])
        arrival_price = request.reference_price if request else None
        fill_price = average_fill_price(events)
        side = request.side if request else None
        estimated_fees = (
            reconciliation.filled_quantity * context.estimated_fee_per_share
            + context.estimated_flat_fee
            if reconciliation.filled_quantity
            else 0.0
        )
        notes: list[str] = []
        limitations = ["paper-only TCA; does not claim live execution quality"]
        if reconciliation.filled_quantity <= 0:
            notes.append("no fill quantity; cost estimate is informational only")
        if arrival_price is None:
            notes.append("tca_input_undisclosed: arrival price missing")
        if fill_price is None:
            notes.append("tca_input_undisclosed: execution price missing")
        slippage_per_unit = (
            fill_price - arrival_price
            if arrival_price is not None and fill_price is not None
            else None
        )
        slippage_total = (
            slippage_per_unit * reconciliation.filled_quantity
            if slippage_per_unit is not None
            else None
        )
        shortfall = implementation_shortfall(
            side=side,
            arrival_price=arrival_price,
            execution_price=fill_price,
            filled_quantity=reconciliation.filled_quantity,
        )
        gross_notional = (
            fill_price * reconciliation.filled_quantity
            if fill_price is not None and reconciliation.filled_quantity
            else None
        )
        estimated_total_cost = (
            shortfall + estimated_fees if shortfall is not None else None
        )
        inputs_disclosed = not (
            reconciliation.filled_quantity > 0
            and (arrival_price is None or fill_price is None)
        )
        estimates.append(
            PostTradeCostEstimate(
                cost_estimate_id=f"ptcost_{uuid4().hex[:12]}",
                reconciliation_id=reconciliation.reconciliation_id,
                symbol=reconciliation.symbol,
                reference_price=arrival_price,
                arrival_price=arrival_price,
                average_fill_price=fill_price,
                execution_price=fill_price,
                side=side,
                filled_quantity=reconciliation.filled_quantity,
                slippage_per_unit=slippage_per_unit,
                slippage_total=slippage_total,
                implementation_shortfall=shortfall,
                gross_notional=gross_notional,
                estimated_fees=estimated_fees,
                estimated_total_cost=estimated_total_cost,
                inputs_disclosed=inputs_disclosed,
                tca_limitations=limitations,
                notes=notes,
            )
        )
    return estimates
