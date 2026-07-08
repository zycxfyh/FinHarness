"""Execution commands — adapter-driven operations.

Commands wire broker adapters to execution services.
submit_order is the canonical submit path: it resolves the adapter,
calls submit, and records the full attempted → submitted → report
lifecycle.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.execution.broker import (
    BrokerAdapter,
    resolve_broker_adapter,
)
from finharness.execution.services import (
    record_execution_report,
    submit_execution_order,
)
from finharness.statecore.execution_models import (
    BrokerConnection,
    ExecutionOrder,
    ExecutionReport,
    OrderDraft,
)


def submit_order(
    *,
    engine: Engine,
    receipt_root: str | Path,
    execution_order_id: str,
) -> ExecutionReport:
    """Submit an execution order through its registered broker adapter.

    1. Resolves the broker connection and its adapter.
    2. Records submit_attempted + submitted via execution services.
    3. Calls adapter.submit_order() to get an ExecutionReport.
    4. Persists the report via record_execution_report.
    5. Returns the recorded ExecutionReport.

    For simulated adapters, the report is synthetic. For live adapters
    (not yet registered), this would contact a real broker API.
    """
    # Resolve order and broker connection
    with Session(engine) as session:
        order = session.exec(
            select(ExecutionOrder).where(
                ExecutionOrder.execution_order_id == execution_order_id
            )
        ).one()
        broker_id = order.broker_connection_id
        draft = session.exec(
            select(OrderDraft).where(
                OrderDraft.order_draft_id == order.order_draft_id
            )
        ).one()

    # Resolve adapter
    adapter = resolve_broker_adapter(broker_id)
    if adapter is None:
        # No adapter registered — still record the full submit lifecycle
        submit_execution_order(
            engine=engine,
            receipt_root=receipt_root,
            execution_order_id=execution_order_id,
            broker_connection_id=broker_id,
        )
        return record_execution_report(
            engine=engine,
            receipt_root=receipt_root,
            execution_order_id=execution_order_id,
            report_type="simulated_submit_ack",
            fill_status="none",
            filled_quantity=None,
            broker_event_ref=f"no_adapter:{execution_order_id}",
        )

    # Record submit lifecycle
    submit_execution_order(
        engine=engine,
        receipt_root=receipt_root,
        execution_order_id=execution_order_id,
        broker_connection_id=broker_id,
    )

    # Call adapter
    report = adapter.submit_order(order, draft)

    # Persist report
    return record_execution_report(
        engine=engine,
        receipt_root=receipt_root,
        execution_order_id=execution_order_id,
        report_type=report.report_type,
        fill_status=report.fill_status,
        filled_quantity=report.filled_quantity,
        average_fill_price=report.average_fill_price,
        broker_event_ref=report.broker_event_ref,
    )
