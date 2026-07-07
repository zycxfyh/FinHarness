"""Simulated broker adapter.

A live-shaped adapter that returns synthetic execution reports.
No real broker SDK, no network, no credentials, no external
connectivity — but the full ExecutionReport shape is real.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from finharness.statecore.execution_models import (
    ExecutionEnvironment,
    ExecutionOrder,
    ExecutionReport,
    OrderDraft,
)


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    import uuid

    return f"{prefix}_{stamp}_{uuid.uuid4().hex[:8]}"


class SimulatedBrokerAdapter:
    """A simulated broker adapter that returns synthetic ExecutionReports.

    This adapter is live-shaped: it produces real ExecutionReport objects
    with valid fill_status, filled_quantity, and average_fill_price fields.
    But no external network, broker API, credential, or venue connectivity
    exists.
    """

    environment: ExecutionEnvironment = ExecutionEnvironment.PAPER

    def __init__(
        self,
        environment: ExecutionEnvironment = ExecutionEnvironment.PAPER,
        simulate_fill: bool = True,
        fill_price_offset: Decimal | None = None,
    ) -> None:
        self.environment = environment
        self.simulate_fill = simulate_fill
        self.fill_price_offset = fill_price_offset

    def submit_order(
        self, order: ExecutionOrder, draft: OrderDraft
    ) -> ExecutionReport:
        """Return a simulated submit acknowledgement.

        If simulate_fill is True, immediately produces a fill report.
        Otherwise returns a submit_ack with fill_status='none'.
        """
        report_id = _new_id("er_sim")
        now = datetime.now(UTC).isoformat()

        if self.simulate_fill:
            price = self._fill_price(draft)
            return ExecutionReport(
                execution_report_id=report_id,
                execution_order_id=order.execution_order_id,
                report_type="simulated_fill",
                fill_status="filled",
                filled_quantity=draft.quantity,
                average_fill_price=price,
                broker_event_ref=f"simulated:fill:{order.execution_order_id}",
                created_at_utc=now,
            )

        return ExecutionReport(
            execution_report_id=report_id,
            execution_order_id=order.execution_order_id,
            report_type="simulated_submit_ack",
            fill_status="none",
            filled_quantity=Decimal("0"),
            average_fill_price=None,
            broker_event_ref=f"simulated:ack:{order.execution_order_id}",
            created_at_utc=now,
        )

    def cancel_order(
        self, order: ExecutionOrder
    ) -> ExecutionReport:
        """Return a simulated cancellation."""
        report_id = _new_id("er_sim_cxl")
        now = datetime.now(UTC).isoformat()
        return ExecutionReport(
            execution_report_id=report_id,
            execution_order_id=order.execution_order_id,
            report_type="simulated_submit_ack",
            fill_status="cancelled",
            filled_quantity=Decimal("0"),
            average_fill_price=None,
            broker_event_ref=f"simulated:cxl:{order.execution_order_id}",
            created_at_utc=now,
        )

    def _fill_price(self, draft: OrderDraft) -> Decimal:
        """Compute a simulated fill price."""
        if draft.limit_price is not None:
            return draft.limit_price
        offset = self.fill_price_offset or Decimal("0")
        base = Decimal("100.00")
        return base + offset
