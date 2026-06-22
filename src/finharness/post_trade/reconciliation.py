"""Lifecycle reconciliation helpers for execution events."""

from __future__ import annotations

from uuid import uuid4

from finharness.execution import ExecutionEvent, ExecutionSnapshot
from finharness.post_trade._constants import PostTradeStatus, TerminalQuantityStatus
from finharness.post_trade._util import now_utc
from finharness.post_trade.models import PostTradeReconciliation


def events_by_order(
    execution_snapshot: ExecutionSnapshot,
) -> dict[str | None, list[ExecutionEvent]]:
    grouped: dict[str | None, list[ExecutionEvent]] = {}
    for item in execution_snapshot.events:
        grouped.setdefault(item.order_request_id, []).append(item)
    return grouped


def status_for_events(events: list[ExecutionEvent]) -> PostTradeStatus:
    statuses = [item.status for item in events]
    filled_quantity = max((item.filled_quantity for item in events), default=0)
    if "partially_filled" in statuses and filled_quantity > 0:
        return "partial_fill_exception"
    if "filled" in statuses:
        return "reconciled_filled"
    if "canceled" in statuses:
        return "reconciled_canceled"
    if "rejected" in statuses:
        return "reconciled_rejected"
    if "blocked_before_submit" in statuses:
        return "needs_human_review"
    if "staged" in statuses and not {"accepted", "submitted_paper"} & set(statuses):
        return "staged_no_trade"
    return "pending_monitoring"


def final_post_trade_status(
    reconciliations: list[PostTradeReconciliation],
    *,
    lineage_ok: bool,
) -> PostTradeStatus:
    if not lineage_ok:
        return "lineage_failed"
    if not reconciliations:
        return "needs_human_review"
    priority: list[PostTradeStatus] = [
        "partial_fill_exception",
        "needs_human_review",
        "reconciled_rejected",
        "reconciled_canceled",
        "reconciled_filled",
        "pending_monitoring",
        "staged_no_trade",
    ]
    statuses = [item.status for item in reconciliations]
    for status in priority:
        if status in statuses:
            return status
    return statuses[-1]


def submitted_quantity_for_events(events: list[ExecutionEvent], requested_quantity: int) -> int:
    submitted_statuses = {
        "submitted_paper",
        "accepted",
        "partially_filled",
        "filled",
        "cancel_requested",
        "canceled",
        "rejected",
    }
    if any(item.status in submitted_statuses for item in events):
        return requested_quantity
    return 0


def terminal_quantity_for_events(
    events: list[ExecutionEvent],
    *,
    requested_quantity: int,
    filled_quantity: int,
    terminal_status: TerminalQuantityStatus,
) -> tuple[int, int]:
    remaining = max(requested_quantity - filled_quantity, 0)
    if terminal_status == "canceled":
        return remaining, 0
    if terminal_status == "rejected":
        return 0, remaining
    return 0, 0


def lifecycle_notes(
    *,
    intended_quantity: int,
    submitted_quantity: int,
    filled_quantity: int,
    canceled_quantity: int,
    rejected_quantity: int,
    remaining_quantity: int,
) -> list[str]:
    notes: list[str] = []
    if submitted_quantity == 0 and intended_quantity > 0:
        notes.append("order was staged but not submitted")
    if remaining_quantity > 0:
        notes.append("remaining quantity is not terminally filled/canceled/rejected")
    terminal_total = filled_quantity + canceled_quantity + rejected_quantity + remaining_quantity
    if terminal_total != intended_quantity:
        notes.append("lifecycle quantity total does not match intended quantity")
    return notes


def build_reconciliations(
    execution_snapshot: ExecutionSnapshot,
) -> list[PostTradeReconciliation]:
    grouped = events_by_order(execution_snapshot)
    reconciliations: list[PostTradeReconciliation] = []
    requests_by_id = {
        request.order_request_id: request for request in execution_snapshot.order_requests
    }
    if not execution_snapshot.order_requests and execution_snapshot.events:
        events = execution_snapshot.events
        filled_quantity = max((item.filled_quantity for item in events), default=0)
        intended_quantity = 0
        submitted_quantity = 0
        canceled_quantity = 0
        rejected_quantity = 0
        remaining_quantity = 0
        reconciliations.append(
            PostTradeReconciliation(
                reconciliation_id=f"ptrec_{uuid4().hex[:12]}",
                intended_quantity=intended_quantity,
                submitted_quantity=submitted_quantity,
                requested_quantity=0,
                filled_quantity=filled_quantity,
                canceled_quantity=canceled_quantity,
                rejected_quantity=rejected_quantity,
                remaining_quantity=remaining_quantity,
                lifecycle_quantity_reconciled=True,
                lifecycle_notes=[],
                status=status_for_events(events),
                execution_statuses=[item.status for item in events],
                execution_event_ids=[item.event_id for item in events],
                created_at_utc=now_utc(),
            )
        )
        return reconciliations
    for request in execution_snapshot.order_requests:
        events = grouped.get(request.order_request_id, [])
        filled_quantity = max((item.filled_quantity for item in events), default=0)
        intended_quantity = requests_by_id[request.order_request_id].quantity
        submitted_quantity = submitted_quantity_for_events(events, intended_quantity)
        status = status_for_events(events)
        terminal_status: TerminalQuantityStatus = "pending_monitoring"
        if status == "reconciled_canceled":
            terminal_status = "canceled"
        elif status == "reconciled_rejected":
            terminal_status = "rejected"
        canceled_quantity, rejected_quantity = terminal_quantity_for_events(
            events,
            requested_quantity=intended_quantity,
            filled_quantity=filled_quantity,
            terminal_status=terminal_status,
        )
        remaining_quantity = max(
            intended_quantity - filled_quantity - canceled_quantity - rejected_quantity,
            0,
        )
        notes = lifecycle_notes(
            intended_quantity=intended_quantity,
            submitted_quantity=submitted_quantity,
            filled_quantity=filled_quantity,
            canceled_quantity=canceled_quantity,
            rejected_quantity=rejected_quantity,
            remaining_quantity=remaining_quantity,
        )
        terminal_total = (
            filled_quantity + canceled_quantity + rejected_quantity + remaining_quantity
        )
        reconciliations.append(
            PostTradeReconciliation(
                reconciliation_id=f"ptrec_{uuid4().hex[:12]}",
                order_request_id=request.order_request_id,
                symbol=request.symbol,
                intended_quantity=intended_quantity,
                submitted_quantity=submitted_quantity,
                requested_quantity=intended_quantity,
                filled_quantity=filled_quantity,
                canceled_quantity=canceled_quantity,
                rejected_quantity=rejected_quantity,
                remaining_quantity=remaining_quantity,
                lifecycle_quantity_reconciled=terminal_total == intended_quantity,
                lifecycle_notes=notes,
                status=status,
                execution_statuses=[item.status for item in events],
                execution_event_ids=[item.event_id for item in events],
                created_at_utc=now_utc(),
            )
        )
    return reconciliations
