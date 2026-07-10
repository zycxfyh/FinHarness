"""Execution services — positive lifecycle operations.

Each function writes to StateCore + produces a receipt. No guardrails,
no negative protection — just the canonical execution lifecycle on a
simulated substrate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.execution.capabilities import (
    DEFAULT_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
    require_execution_capability,
)
from finharness.execution.receipts import (
    write_execution_receipt,
)
from finharness.statecore.execution_models import (
    ApprovalRecord,
    ExecutionEnvironment,
    ExecutionOrder,
    ExecutionReport,
    OrderDraft,
    PositionDelta,
    PreTradeCheck,
    ReconciliationReport,
)
from finharness.statecore.models import ReceiptIndex
from finharness.statecore.proposals import _display_path
from finharness.statecore.store import write_records

# ── Helpers ─────────────────────────────────────────────────────────────────


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{_stamp()}_{uuid4().hex[:8]}"


# ── Service functions ───────────────────────────────────────────────────────


def create_order_draft(
    *,
    engine: Engine,
    receipt_root: str | Path,
    execution_account_id: str,
    instrument_ref: str,
    symbol: str,
    side: str,
    order_type: str,
    quantity: Decimal,
    rationale: str,
    environment: str = "live",
    time_in_force: str = "day",
    limit_price: Decimal | None = None,
    stop_price: Decimal | None = None,
    proposal_id: str | None = None,
    source_kind: str = "",
    source_ref: str = "",
    capabilities: ExecutionCapabilities = DEFAULT_EXECUTION_CAPABILITIES,
) -> OrderDraft:
    """Create an order draft — the canonical entry point for execution."""
    require_execution_capability(capabilities, "create_order_draft")
    draft_id = _new_id("od")
    created = _now_utc()

    draft = OrderDraft(
        order_draft_id=draft_id,
        proposal_id=proposal_id,
        environment=ExecutionEnvironment(environment),
        execution_account_id=execution_account_id,
        instrument_ref=instrument_ref,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=quantity,
        limit_price=limit_price,
        stop_price=stop_price,
        time_in_force=time_in_force,
        rationale=rationale,
        source_kind=source_kind,
        source_ref=source_ref,
        draft_status="draft",
        created_at_utc=created,
    )

    receipt_id, receipt_path = write_execution_receipt(
        receipt_root=receipt_root,
        kind="execution.order_draft.created",
        artifact_id=draft_id,
        payload={
            "side": side,
            "symbol": symbol,
            "order_type": order_type,
            "quantity": str(quantity),
            "environment": environment,
        },
    )
    draft.receipt_ref = receipt_id

    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="execution.order_draft.created",
        path=_display_path(Path(receipt_path)),
        created_at_utc=created,
        refs=[draft_id],
    )

    write_records([draft, index], engine=engine)
    return draft


def run_pretrade_check(
    *,
    engine: Engine,
    receipt_root: str | Path,
    order_draft_id: str,
    findings: list[dict[str, Any]] | None = None,
    required_approval_level: str = "human",
    capabilities: ExecutionCapabilities = DEFAULT_EXECUTION_CAPABILITIES,
) -> PreTradeCheck:
    """Run a pre-trade check against an order draft."""
    require_execution_capability(capabilities, "run_pretrade_check")
    check_id = _new_id("ptc")
    created = _now_utc()
    findings_json = __import__("json").dumps(findings or [])

    status = "pass"
    for f in findings or []:
        if f.get("severity") == "block":
            status = "block"
            break
        elif f.get("severity") == "warn":
            status = "warn"

    check = PreTradeCheck(
        pretrade_check_id=check_id,
        order_draft_id=order_draft_id,
        check_status=status,
        findings_json=findings_json,
        required_approval_level=required_approval_level,
        created_at_utc=created,
    )

    receipt_id, receipt_path = write_execution_receipt(
        receipt_root=receipt_root,
        kind="execution.pretrade_check.recorded",
        artifact_id=check_id,
        payload={"order_draft_id": order_draft_id, "status": status},
    )
    check.receipt_ref = receipt_id

    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="execution.pretrade_check.recorded",
        path=_display_path(Path(receipt_path)),
        created_at_utc=created,
        refs=[check_id, order_draft_id],
    )

    # Update draft status
    with Session(engine) as session:
        draft = session.exec(
            select(OrderDraft).where(OrderDraft.order_draft_id == order_draft_id)
        ).one_or_none()
        if draft:
            draft.draft_status = (
                "pretrade_check_passed" if status == "pass" else "pretrade_check_blocked"
            )
            session.add(draft)
            session.commit()

    write_records([check, index], engine=engine)
    return check


def record_approval(
    *,
    engine: Engine,
    receipt_root: str | Path,
    order_draft_id: str,
    decision: str,
    reviewer_id: str,
    rationale: str,
    capabilities: ExecutionCapabilities = DEFAULT_EXECUTION_CAPABILITIES,
) -> ApprovalRecord:
    """Record a human approval decision on an order draft."""
    require_execution_capability(capabilities, "record_approval")
    approval_id = _new_id("appr")
    created = _now_utc()

    approval = ApprovalRecord(
        approval_id=approval_id,
        order_draft_id=order_draft_id,
        decision=decision,
        reviewer_id=reviewer_id,
        rationale=rationale,
        created_at_utc=created,
    )

    receipt_id, receipt_path = write_execution_receipt(
        receipt_root=receipt_root,
        kind="execution.approval.recorded",
        artifact_id=approval_id,
        payload={
            "order_draft_id": order_draft_id,
            "decision": decision,
            "reviewer_id": reviewer_id,
        },
    )
    approval.receipt_ref = receipt_id

    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="execution.approval.recorded",
        path=_display_path(Path(receipt_path)),
        created_at_utc=created,
        refs=[approval_id, order_draft_id],
    )

    # Update draft status
    with Session(engine) as session:
        draft = session.exec(
            select(OrderDraft).where(OrderDraft.order_draft_id == order_draft_id)
        ).one_or_none()
        if draft:
            draft.draft_status = "approved" if decision == "approved" else "rejected"
            session.add(draft)
            session.commit()

    write_records([approval, index], engine=engine)
    return approval


def stage_execution_order(
    *,
    engine: Engine,
    receipt_root: str | Path,
    order_draft_id: str,
    broker_connection_id: str,
    environment: str = "live",
    capabilities: ExecutionCapabilities = DEFAULT_EXECUTION_CAPABILITIES,
) -> ExecutionOrder:
    """Stage an execution order from an approved draft.

    Raises ValueError if draft is rejected, cancelled, not pretrade-checked,
    or not yet approved.
    """
    require_execution_capability(capabilities, "stage_execution_order")
    # ── pre-conditions ──
    with Session(engine) as session:
        draft = session.exec(
            select(OrderDraft).where(OrderDraft.order_draft_id == order_draft_id)
        ).one_or_none()
        if draft is None:
            raise ValueError(f"order draft not found: {order_draft_id}")
        if draft.draft_status in ("rejected", "cancelled"):
            raise ValueError(f"cannot stage {draft.draft_status} draft: {order_draft_id}")
        if draft.draft_status != "approved":
            raise ValueError(
                f"draft must be approved before staging: current status={draft.draft_status}"
            )

        # Verify PreTradeCheck exists and is not blocked
        ptc = session.exec(
            select(PreTradeCheck).where(PreTradeCheck.order_draft_id == order_draft_id)
        ).first()
        if ptc is None:
            raise ValueError(f"no PreTradeCheck found for draft: {order_draft_id}")
        if ptc.check_status == "block":
            raise ValueError(f"cannot stage blocked pretrade check: {order_draft_id}")

        # Verify ApprovalRecord exists
        approval = session.exec(
            select(ApprovalRecord).where(ApprovalRecord.order_draft_id == order_draft_id)
        ).first()
        if approval is None:
            raise ValueError(f"no ApprovalRecord found for draft: {order_draft_id}")

        env_val = draft.environment
        actual_env = env_val.value if hasattr(env_val, "value") else str(env_val)

    order_id = _new_id("eo")
    created = _now_utc()

    order = ExecutionOrder(
        execution_order_id=order_id,
        order_draft_id=order_draft_id,
        broker_connection_id=broker_connection_id,
        environment=ExecutionEnvironment(actual_env),
        execution_status="staged",
        created_at_utc=created,
    )

    receipt_id, receipt_path = write_execution_receipt(
        receipt_root=receipt_root,
        kind="execution.order.staged",
        artifact_id=order_id,
        payload={
            "order_draft_id": order_draft_id,
            "broker_connection_id": broker_connection_id,
            "environment": environment,
        },
    )
    order.receipt_ref = receipt_id

    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="execution.order.staged",
        path=_display_path(Path(receipt_path)),
        created_at_utc=created,
        refs=[order_id, order_draft_id],
    )

    # Update draft status
    with Session(engine) as session:
        draft = session.exec(
            select(OrderDraft).where(OrderDraft.order_draft_id == order_draft_id)
        ).one_or_none()
        if draft:
            draft.draft_status = "staged"
            session.add(draft)
            session.commit()

    write_records([order, index], engine=engine)
    return order


def submit_execution_order(
    *,
    engine: Engine,
    receipt_root: str | Path,
    execution_order_id: str,
    broker_connection_id: str,
    capabilities: ExecutionCapabilities = DEFAULT_EXECUTION_CAPABILITIES,
) -> ExecutionOrder:
    """Submit an execution order to the broker adapter.

    The actual submission is handled by a BrokerAdapter. This service
    records the submit attempted → submitted lifecycle. For simulated
    adapters, no external network call occurs.

    Raises ValueError if the order is not in 'staged' status.
    """
    require_execution_capability(capabilities, "submit_simulated_order")
    # ── pre-condition: must be staged ──
    with Session(engine) as session:
        order_check = session.exec(
            select(ExecutionOrder).where(ExecutionOrder.execution_order_id == execution_order_id)
        ).one_or_none()
        if order_check is None:
            raise ValueError(f"execution order not found: {execution_order_id}")
        if order_check.execution_status != "staged":
            raise ValueError(
                f"cannot submit order with status '{order_check.execution_status}': "
                f"must be 'staged', got '{order_check.execution_status}'"
            )

    created = _now_utc()

    # ── submit_attempted receipt ──
    attempted_id, attempted_path = write_execution_receipt(
        receipt_root=receipt_root,
        kind="execution.order.submit_attempted",
        artifact_id=execution_order_id,
        payload={
            "broker_connection_id": broker_connection_id,
            "attempted_at_utc": created,
        },
    )
    attempted_index = ReceiptIndex(
        receipt_id=attempted_id,
        kind="execution.order.submit_attempted",
        path=_display_path(Path(attempted_path)),
        created_at_utc=created,
        refs=[execution_order_id],
    )

    # ── update status to submitted ──
    with Session(engine, expire_on_commit=False) as session:
        order = session.exec(
            select(ExecutionOrder).where(ExecutionOrder.execution_order_id == execution_order_id)
        ).one()
        order.execution_status = "submitted"
        order.submitted_at_utc = created
        session.add(order)
        session.commit()

    # ── submitted receipt ──
    submitted_id, submitted_path = write_execution_receipt(
        receipt_root=receipt_root,
        kind="execution.order.submitted",
        artifact_id=execution_order_id,
        payload={
            "broker_connection_id": broker_connection_id,
            "submitted_at_utc": created,
        },
    )
    submitted_index = ReceiptIndex(
        receipt_id=submitted_id,
        kind="execution.order.submitted",
        path=_display_path(Path(submitted_path)),
        created_at_utc=created,
        refs=[execution_order_id],
    )

    # ── persist receipt_ref on the order row ──
    order.receipt_ref = submitted_id
    write_records([order, attempted_index, submitted_index], engine=engine)
    return order


def record_execution_report(
    *,
    engine: Engine,
    receipt_root: str | Path,
    execution_order_id: str,
    report_type: str,
    fill_status: str = "none",
    filled_quantity: Decimal | None = None,
    average_fill_price: Decimal | None = None,
    broker_event_ref: str | None = None,
) -> ExecutionReport:
    """Record a broker execution report (real or simulated)."""
    report_id = _new_id("er")
    created = _now_utc()

    report = ExecutionReport(
        execution_report_id=report_id,
        execution_order_id=execution_order_id,
        report_type=report_type,
        fill_status=fill_status,
        filled_quantity=filled_quantity or Decimal("0"),
        average_fill_price=average_fill_price,
        broker_event_ref=broker_event_ref,
        created_at_utc=created,
    )

    receipt_id, receipt_path = write_execution_receipt(
        receipt_root=receipt_root,
        kind="execution.report.recorded",
        artifact_id=report_id,
        payload={
            "execution_order_id": execution_order_id,
            "report_type": report_type,
            "fill_status": fill_status,
            "filled_quantity": str(report.filled_quantity),
        },
    )
    report.receipt_ref = receipt_id

    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="execution.report.recorded",
        path=_display_path(Path(receipt_path)),
        created_at_utc=created,
        refs=[report_id, execution_order_id],
    )

    # Update execution order status
    with Session(engine) as session:
        order = session.exec(
            select(ExecutionOrder).where(ExecutionOrder.execution_order_id == execution_order_id)
        ).one_or_none()
        if order:
            if fill_status == "filled":
                order.execution_status = "filled"
            elif fill_status == "partial":
                order.execution_status = "partial_fill"
            session.add(order)
            session.commit()

    write_records([report, index], engine=engine)
    return report


def record_position_delta(
    *,
    engine: Engine,
    receipt_root: str | Path,
    execution_report_id: str,
    execution_account_id: str,
    symbol: str,
    delta_quantity: Decimal,
    post_execution_quantity: Decimal,
) -> PositionDelta:
    """Record a position change resulting from an execution report."""
    delta_id = _new_id("pd")
    created = _now_utc()

    delta = PositionDelta(
        position_delta_id=delta_id,
        execution_report_id=execution_report_id,
        execution_account_id=execution_account_id,
        symbol=symbol,
        delta_quantity=delta_quantity,
        post_execution_quantity=post_execution_quantity,
        created_at_utc=created,
    )

    receipt_id, receipt_path = write_execution_receipt(
        receipt_root=receipt_root,
        kind="execution.position_delta.recorded",
        artifact_id=delta_id,
        payload={
            "symbol": symbol,
            "delta_quantity": str(delta_quantity),
            "post_execution_quantity": str(post_execution_quantity),
        },
    )
    delta.receipt_ref = receipt_id

    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="execution.position_delta.recorded",
        path=_display_path(Path(receipt_path)),
        created_at_utc=created,
        refs=[delta_id, execution_report_id],
    )

    write_records([delta, index], engine=engine)
    return delta


def record_reconciliation(
    *,
    engine: Engine,
    receipt_root: str | Path,
    execution_account_id: str,
    expected_positions: list[dict[str, Any]] | None = None,
    actual_positions: list[dict[str, Any]] | None = None,
    discrepancies: list[dict[str, Any]] | None = None,
) -> ReconciliationReport:
    """Record a reconciliation report comparing expected vs actual positions."""
    import json

    rec_id = _new_id("rec")
    created = _now_utc()
    expected_json = json.dumps(expected_positions or [])
    actual_json = json.dumps(actual_positions or [])
    disc_json = json.dumps(discrepancies or [])

    status = "matched" if not (discrepancies or []) else "unmatched"

    rec = ReconciliationReport(
        reconciliation_id=rec_id,
        execution_account_id=execution_account_id,
        reconciliation_status=status,
        expected_positions_json=expected_json,
        actual_positions_json=actual_json,
        discrepancies_json=disc_json,
        created_at_utc=created,
    )

    receipt_id, receipt_path = write_execution_receipt(
        receipt_root=receipt_root,
        kind="execution.reconciliation.recorded",
        artifact_id=rec_id,
        payload={
            "execution_account_id": execution_account_id,
            "status": status,
        },
    )
    rec.receipt_ref = receipt_id

    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="execution.reconciliation.recorded",
        path=_display_path(Path(receipt_path)),
        created_at_utc=created,
        refs=[rec_id, execution_account_id],
    )

    write_records([rec, index], engine=engine)
    return rec
