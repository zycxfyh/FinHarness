"""Execution API routes.

Canonical execution surface: order draft, pre-trade check, approval,
stage, submit, order read, report read. These routes use the positive
execution lifecycle — no "not live" protection, no avoidance of
order/broker/submit/execution/live terminology.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from finharness.api.dependencies import (
    EngineDependency,
    ReceiptRootDependency,
    WriteCapabilityDependency,
)
from finharness.execution.commands import submit_order
from finharness.execution.services import (
    create_order_draft,
    record_approval,
    run_pretrade_check,
    stage_execution_order,
)
from finharness.statecore.execution_models import (
    ExecutionOrder,
    ExecutionReport,
)

router = APIRouter(prefix="/execution", tags=["execution"])


# ── Request models ──────────────────────────────────────────────────────────


class CreateOrderDraftRequest(BaseModel):
    execution_account_id: str
    instrument_ref: str
    symbol: str
    side: str
    order_type: str
    quantity: str
    rationale: str
    environment: str = "live"
    time_in_force: str = "day"
    limit_price: str | None = None
    stop_price: str | None = None
    proposal_id: str | None = None
    source_kind: str = ""
    source_ref: str = ""


class RunPreTradeCheckRequest(BaseModel):
    findings: list[dict[str, Any]] | None = None
    required_approval_level: str = "human"


class RecordApprovalRequest(BaseModel):
    decision: str
    reviewer_id: str
    rationale: str


class StageOrderRequest(BaseModel):
    broker_connection_id: str
    environment: str = "live"


class SubmitOrderRequest(BaseModel):
    pass  # broker_connection_id is resolved from the order


# ── Routes ──────────────────────────────────────────────────────────────────


@router.post("/order-drafts")
def api_create_order_draft(
    body: CreateOrderDraftRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write: WriteCapabilityDependency,
) -> dict[str, Any]:
    """Create an order draft."""
    draft = create_order_draft(
        engine=engine,
        receipt_root=receipt_root,
        execution_account_id=body.execution_account_id,
        instrument_ref=body.instrument_ref,
        symbol=body.symbol,
        side=body.side,
        order_type=body.order_type,
        quantity=Decimal(body.quantity),
        rationale=body.rationale,
        environment=body.environment,
        time_in_force=body.time_in_force,
        limit_price=Decimal(body.limit_price) if body.limit_price else None,
        stop_price=Decimal(body.stop_price) if body.stop_price else None,
        proposal_id=body.proposal_id,
        source_kind=body.source_kind,
        source_ref=body.source_ref,
    )
    return {
        "order_draft_id": draft.order_draft_id,
        "side": draft.side,
        "symbol": draft.symbol,
        "order_type": draft.order_type,
        "quantity": str(draft.quantity),
        "environment": draft.environment.value
        if hasattr(draft.environment, "value")
        else str(draft.environment),
        "draft_status": draft.draft_status,
        "receipt_ref": draft.receipt_ref,
    }


@router.post("/order-drafts/{order_draft_id}/pretrade-checks")
def api_run_pretrade_check(
    order_draft_id: str,
    body: RunPreTradeCheckRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write: WriteCapabilityDependency,
) -> dict[str, Any]:
    """Run a pre-trade check on an order draft."""
    check = run_pretrade_check(
        engine=engine,
        receipt_root=receipt_root,
        order_draft_id=order_draft_id,
        findings=body.findings,
        required_approval_level=body.required_approval_level,
    )
    return {
        "pretrade_check_id": check.pretrade_check_id,
        "check_status": check.check_status,
        "receipt_ref": check.receipt_ref,
    }


@router.post("/order-drafts/{order_draft_id}/approvals")
def api_record_approval(
    order_draft_id: str,
    body: RecordApprovalRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write: WriteCapabilityDependency,
) -> dict[str, Any]:
    """Record an approval decision."""
    approval = record_approval(
        engine=engine,
        receipt_root=receipt_root,
        order_draft_id=order_draft_id,
        decision=body.decision,
        reviewer_id=body.reviewer_id,
        rationale=body.rationale,
    )
    return {
        "approval_id": approval.approval_id,
        "decision": approval.decision,
        "receipt_ref": approval.receipt_ref,
    }


@router.post("/order-drafts/{order_draft_id}/stage")
def api_stage_order(
    order_draft_id: str,
    body: StageOrderRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write: WriteCapabilityDependency,
) -> dict[str, Any]:
    """Stage an execution order."""
    order = stage_execution_order(
        engine=engine,
        receipt_root=receipt_root,
        order_draft_id=order_draft_id,
        broker_connection_id=body.broker_connection_id,
        environment=body.environment,
    )
    return {
        "execution_order_id": order.execution_order_id,
        "execution_status": order.execution_status,
        "broker_connection_id": order.broker_connection_id,
        "environment": order.environment.value
        if hasattr(order.environment, "value")
        else str(order.environment),
        "receipt_ref": order.receipt_ref,
    }


@router.post("/orders/{execution_order_id}/submit")
def api_submit_order(
    execution_order_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write: WriteCapabilityDependency,
) -> dict[str, Any]:
    """Submit an execution order through its broker adapter."""
    report = submit_order(
        engine=engine,
        receipt_root=receipt_root,
        execution_order_id=execution_order_id,
    )
    return {
        "execution_report_id": report.execution_report_id,
        "execution_order_id": report.execution_order_id,
        "report_type": report.report_type,
        "fill_status": report.fill_status,
        "filled_quantity": str(report.filled_quantity),
        "average_fill_price": str(report.average_fill_price)
        if report.average_fill_price
        else None,
        "receipt_ref": report.receipt_ref,
    }


@router.get("/orders/{execution_order_id}")
def api_get_order(
    execution_order_id: str,
    engine: EngineDependency,
) -> dict[str, Any] | None:
    """Read a single execution order."""
    with Session(engine) as session:
        order = session.exec(
            select(ExecutionOrder).where(
                ExecutionOrder.execution_order_id == execution_order_id
            )
        ).one_or_none()
        if order is None:
            raise HTTPException(status_code=404, detail="Execution order not found")
        return {
            "execution_order_id": order.execution_order_id,
            "order_draft_id": order.order_draft_id,
            "broker_connection_id": order.broker_connection_id,
            "environment": order.environment.value
            if hasattr(order.environment, "value")
            else str(order.environment),
            "execution_status": order.execution_status,
            "submitted_at_utc": order.submitted_at_utc,
            "broker_order_ref": order.broker_order_ref,
            "receipt_ref": order.receipt_ref,
        }


@router.get("/orders")
def api_list_orders(
    engine: EngineDependency,
    offset: int = 0,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List execution orders."""
    with Session(engine) as session:
        orders = session.exec(
            select(ExecutionOrder)
            .order_by(ExecutionOrder.created_at_utc.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return [
            {
                "execution_order_id": o.execution_order_id,
                "order_draft_id": o.order_draft_id,
                "broker_connection_id": o.broker_connection_id,
                "environment": o.environment.value
                if hasattr(o.environment, "value")
                else str(o.environment),
                "execution_status": o.execution_status,
                "submitted_at_utc": o.submitted_at_utc,
                "receipt_ref": o.receipt_ref,
            }
            for o in orders
        ]


@router.get("/reports/{execution_report_id}")
def api_get_report(
    execution_report_id: str,
    engine: EngineDependency,
) -> dict[str, Any]:
    """Read a single execution report."""
    with Session(engine) as session:
        report = session.exec(
            select(ExecutionReport).where(
                ExecutionReport.execution_report_id == execution_report_id
            )
        ).one_or_none()
        if report is None:
            raise HTTPException(status_code=404, detail="Execution report not found")
        return {
            "execution_report_id": report.execution_report_id,
            "execution_order_id": report.execution_order_id,
            "report_type": report.report_type,
            "fill_status": report.fill_status,
            "filled_quantity": str(report.filled_quantity),
            "average_fill_price": str(report.average_fill_price)
            if report.average_fill_price
            else None,
            "broker_event_ref": report.broker_event_ref,
            "receipt_ref": report.receipt_ref,
        }
