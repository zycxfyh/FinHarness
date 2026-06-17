"""Tenth-layer post-trade reconciliation and review governance.

Post-Trade consumes Execution evidence and produces reconciliation, cost,
exception, and handoff state. It never creates, modifies, cancels, or resubmits
orders.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.execution import (
    ExecutionEvent,
    ExecutionOrderRequest,
    ExecutionSnapshot,
    ExecutionStatus,
)
from finharness.market_data import ROOT, sha256_text

POST_TRADE_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "post-trade"
POST_TRADE_RECEIPT_ROOT = ROOT / "data" / "receipts" / "post-trade"

PostTradeStatus = Literal[
    "pending_monitoring",
    "reconciled_filled",
    "reconciled_canceled",
    "reconciled_rejected",
    "partial_fill_exception",
    "staged_no_trade",
    "lineage_failed",
    "needs_human_review",
]
PostTradeExceptionSeverity = Literal["info", "warning", "critical"]


class PostTradeSourceSpec(BaseModel):
    """Source/config layer for post-trade processing."""

    model_config = ConfigDict(frozen=True)

    provider: str = "FinHarness deterministic post-trade"
    method: str = "post_trade_reconciliation_mvp"
    input_layer: str = "execution"
    template_version: str = "finharness.post_trade.template.v1"
    config: dict[str, Any] = Field(default_factory=dict)


class PostTradeContext(BaseModel):
    """Post-trade assumptions and accounting handoff context."""

    model_config = ConfigDict(frozen=True)

    mandate_id: str = "paper_post_trade_review_v1"
    # Fail-closed: attestation is an action a human takes, never a default.
    human_review_attested: bool = False
    estimated_fee_per_share: float = 0.0
    estimated_flat_fee: float = 0.0
    settlement_cycle: str = "paper_no_settlement"
    account_ref: str | None = "paper_account"
    custody_ref: str | None = None
    performance_handoff_enabled: bool = True


class PostTradeReconciliation(BaseModel):
    """Requested versus executed state for one order request."""

    model_config = ConfigDict(frozen=True)

    reconciliation_id: str
    order_request_id: str | None = None
    symbol: str | None = None
    intended_quantity: int
    submitted_quantity: int
    requested_quantity: int
    filled_quantity: int
    canceled_quantity: int = 0
    rejected_quantity: int = 0
    remaining_quantity: int
    lifecycle_quantity_reconciled: bool
    lifecycle_notes: list[str] = Field(default_factory=list)
    status: PostTradeStatus
    execution_statuses: list[str]
    execution_event_ids: list[str]
    created_at_utc: str


class PostTradeCostEstimate(BaseModel):
    """Conservative TCA/slippage estimate for available fill evidence."""

    model_config = ConfigDict(frozen=True)

    cost_estimate_id: str
    reconciliation_id: str
    symbol: str | None = None
    reference_price: float | None = None
    arrival_price: float | None = None
    average_fill_price: float | None = None
    execution_price: float | None = None
    side: Literal["buy", "sell"] | None = None
    filled_quantity: int
    slippage_per_unit: float | None = None
    slippage_total: float | None = None
    implementation_shortfall: float | None = None
    gross_notional: float | None = None
    estimated_fees: float
    estimated_total_cost: float | None = None
    inputs_disclosed: bool
    tca_limitations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PostTradeException(BaseModel):
    """Reviewable post-trade exception."""

    model_config = ConfigDict(frozen=True)

    exception_id: str
    exception_type: str
    severity: PostTradeExceptionSeverity
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    created_at_utc: str


class PostTradeQuality(BaseModel):
    """Quality gates for post-trade output."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    execution_lineage_present: bool
    execution_receipt_present: bool
    no_order_creation: bool
    final_execution_state_classified: bool
    filled_quantity_reconciled: bool
    partial_fill_exception_preserved: bool
    reject_cancel_exception_preserved: bool
    tca_inputs_disclosed: bool
    handoff_state_present: bool
    receipt_written: bool
    notes: list[str] = Field(default_factory=list)


class PostTradeLineage(BaseModel):
    """Lineage from ExecutionSnapshot into post-trade output."""

    model_config = ConfigDict(frozen=True)

    source: PostTradeSourceSpec
    input_execution_snapshot_id: str
    input_execution_receipt_ref: str
    execution_event_ids: list[str]
    execution_final_status: str
    post_trade_status: PostTradeStatus
    computed_at_utc: str
    transform_version: str = "finharness.post_trade.v1"
    output_hash: str
    output_ref: str


class PostTradeSnapshot(BaseModel):
    """Stable tenth-layer post-trade evidence."""

    model_config = ConfigDict(frozen=True)

    post_trade_snapshot_id: str
    as_of_utc: str
    input_execution_snapshot_id: str
    input_execution_receipt_ref: str
    final_status: PostTradeStatus
    reconciliation_count: int
    cost_estimate_count: int
    exception_count: int
    reconciliations: list[PostTradeReconciliation]
    cost_estimates: list[PostTradeCostEstimate]
    exceptions: list[PostTradeException]
    quality: PostTradeQuality
    lineage: PostTradeLineage
    payload_ref: str
    receipt_ref: str
    order_creation_allowed: bool = False
    portfolio_handoff: list[str] = Field(default_factory=list)
    accounting_handoff: list[str] = Field(default_factory=list)
    performance_handoff: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class PostTradeReceipt(BaseModel):
    """Durable evidence root for tenth-layer post-trade processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "post_trade_processing"
    stage_flow: dict[str, str]
    snapshot: PostTradeSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class PostTradeBundle(BaseModel):
    """Compact handoff for scripts and graph nodes."""

    model_config = ConfigDict(frozen=True)

    source: PostTradeSourceSpec
    input_execution_snapshot: ExecutionSnapshot
    context: PostTradeContext
    reconciliations: list[PostTradeReconciliation]
    cost_estimates: list[PostTradeCostEstimate]
    exceptions: list[PostTradeException]
    quality: PostTradeQuality
    lineage: PostTradeLineage
    snapshot: PostTradeSnapshot
    receipt: PostTradeReceipt


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def exception(
    *,
    exception_type: str,
    severity: PostTradeExceptionSeverity,
    reason: str,
    evidence_refs: list[str] | None = None,
) -> PostTradeException:
    return PostTradeException(
        exception_id=f"ptexc_{uuid4().hex[:12]}",
        exception_type=exception_type,
        severity=severity,
        reason=reason,
        evidence_refs=evidence_refs or [],
        created_at_utc=now_utc(),
    )


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
    terminal_status: ExecutionStatus,
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
        terminal_status = "pending_monitoring"
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


def build_post_trade_exceptions(
    *,
    execution_snapshot: ExecutionSnapshot,
    reconciliations: list[PostTradeReconciliation],
    cost_estimates: list[PostTradeCostEstimate],
) -> list[PostTradeException]:
    exceptions: list[PostTradeException] = []
    refs = [execution_snapshot.payload_ref, execution_snapshot.receipt_ref]
    for reconciliation in reconciliations:
        evidence = [*refs, *reconciliation.execution_event_ids]
        if reconciliation.status == "partial_fill_exception":
            exceptions.append(
                exception(
                    exception_type="partial_fill",
                    severity="warning",
                    reason="Partial fill requires review before portfolio handoff.",
                    evidence_refs=evidence,
                )
            )
        elif reconciliation.status == "reconciled_rejected":
            exceptions.append(
                exception(
                    exception_type="execution_rejected",
                    severity="warning",
                    reason="Execution adapter rejected the order request.",
                    evidence_refs=evidence,
                )
            )
        elif reconciliation.status == "reconciled_canceled":
            exceptions.append(
                exception(
                    exception_type="execution_canceled",
                    severity="info",
                    reason="Execution was canceled; no clean fill handoff.",
                    evidence_refs=evidence,
                )
            )
        elif reconciliation.status == "staged_no_trade":
            exceptions.append(
                exception(
                    exception_type="staged_no_trade",
                    severity="info",
                    reason="Order-shaped request was staged only and is not a trade.",
                    evidence_refs=evidence,
                )
            )
        elif reconciliation.status == "pending_monitoring":
            exceptions.append(
                exception(
                    exception_type="pending_monitoring",
                    severity="info",
                    reason="Execution lifecycle is not terminal yet.",
                    evidence_refs=evidence,
                )
            )
        elif reconciliation.status == "needs_human_review":
            exceptions.append(
                exception(
                    exception_type="blocked_before_submit",
                    severity="critical",
                    reason="Execution was blocked before submit and needs review.",
                    evidence_refs=evidence,
                )
            )
    for estimate in cost_estimates:
        if estimate.filled_quantity > 0 and (
            estimate.reference_price is None or estimate.average_fill_price is None
        ):
            exceptions.append(
                exception(
                    exception_type="missing_tca_price_input",
                    severity="warning",
                    reason="Filled quantity exists but TCA price inputs are incomplete.",
                    evidence_refs=refs,
                )
            )
    if not execution_snapshot.receipt_ref:
        exceptions.append(
            exception(
                exception_type="missing_execution_receipt",
                severity="critical",
                reason="Execution receipt reference is missing.",
                evidence_refs=[execution_snapshot.execution_snapshot_id],
            )
        )
    return exceptions


def build_post_trade_quality(
    *,
    execution_snapshot: ExecutionSnapshot,
    reconciliations: list[PostTradeReconciliation],
    cost_estimates: list[PostTradeCostEstimate],
    exceptions: list[PostTradeException],
    lineage_complete: bool = True,
    receipt_written: bool = True,
) -> PostTradeQuality:
    notes: list[str] = []
    execution_lineage_present = bool(
        execution_snapshot.execution_snapshot_id
        and execution_snapshot.lineage.input_risk_gate_snapshot_id
    )
    execution_receipt_present = bool(execution_snapshot.receipt_ref)
    no_order_creation = True
    final_execution_state_classified = bool(reconciliations)
    filled_quantity_reconciled = all(
        item.lifecycle_quantity_reconciled
        and (
            item.filled_quantity
            + item.canceled_quantity
            + item.rejected_quantity
            + item.remaining_quantity
            == item.intended_quantity
        )
        for item in reconciliations
    )
    has_partial = any(
        event.status == "partially_filled" for event in execution_snapshot.events
    )
    partial_fill_exception_preserved = (
        not has_partial
        or any(item.status == "partial_fill_exception" for item in reconciliations)
        or any(item.exception_type == "partial_fill" for item in exceptions)
    )
    has_reject_or_cancel = any(
        event.status in {"rejected", "canceled"} for event in execution_snapshot.events
    )
    reject_cancel_exception_preserved = (
        not has_reject_or_cancel
        or any(
            item.exception_type in {"execution_rejected", "execution_canceled"}
            for item in exceptions
        )
    )
    tca_inputs_disclosed = all(item.inputs_disclosed for item in cost_estimates)
    handoff_state_present = bool(
        reconciliations
        and any(
            item.status
            in {
                "reconciled_filled",
                "reconciled_canceled",
                "reconciled_rejected",
                "partial_fill_exception",
                "staged_no_trade",
                "pending_monitoring",
                "needs_human_review",
            }
            for item in reconciliations
        )
    )
    if not execution_receipt_present:
        notes.append("execution receipt reference missing")
    ok = (
        execution_lineage_present
        and execution_receipt_present
        and no_order_creation
        and final_execution_state_classified
        and filled_quantity_reconciled
        and partial_fill_exception_preserved
        and reject_cancel_exception_preserved
        and tca_inputs_disclosed
        and handoff_state_present
        and lineage_complete
        and receipt_written
    )
    return PostTradeQuality(
        ok=ok,
        execution_lineage_present=execution_lineage_present,
        execution_receipt_present=execution_receipt_present,
        no_order_creation=no_order_creation,
        final_execution_state_classified=final_execution_state_classified,
        filled_quantity_reconciled=filled_quantity_reconciled,
        partial_fill_exception_preserved=partial_fill_exception_preserved,
        reject_cancel_exception_preserved=reject_cancel_exception_preserved,
        tca_inputs_disclosed=tca_inputs_disclosed,
        handoff_state_present=handoff_state_present,
        receipt_written=receipt_written,
        notes=notes,
    )


def portfolio_handoff(reconciliations: list[PostTradeReconciliation]) -> list[str]:
    filled = [
        item
        for item in reconciliations
        if item.status == "reconciled_filled" and item.filled_quantity > 0
    ]
    return [
        f"{item.symbol}: filled_quantity={item.filled_quantity}; review paper position"
        for item in filled
    ]


def accounting_handoff(status: PostTradeStatus, context: PostTradeContext) -> list[str]:
    if status == "reconciled_filled":
        return [
            f"paper accounting review only; settlement_cycle={context.settlement_cycle}"
        ]
    if status in {"reconciled_canceled", "reconciled_rejected", "staged_no_trade"}:
        return ["no accounting position; retain exception evidence"]
    return ["accounting handoff blocked pending exception review"]


def performance_handoff(
    *,
    status: PostTradeStatus,
    context: PostTradeContext,
    cost_estimates: list[PostTradeCostEstimate],
) -> list[str]:
    if not context.performance_handoff_enabled:
        return []
    if status == "reconciled_filled":
        return [
            f"{item.symbol}: estimated_total_cost={item.estimated_total_cost}"
            for item in cost_estimates
            if item.filled_quantity > 0
        ]
    return ["performance attribution waits for reconciled fill"]


def persist_post_trade_bundle(
    *,
    source: PostTradeSourceSpec,
    input_execution_snapshot: ExecutionSnapshot,
    context: PostTradeContext,
    reconciliations: list[PostTradeReconciliation],
    cost_estimates: list[PostTradeCostEstimate],
    exceptions: list[PostTradeException],
) -> PostTradeBundle:
    lineage_ok = bool(input_execution_snapshot.receipt_ref)
    final_status = final_post_trade_status(reconciliations, lineage_ok=lineage_ok)
    quality = build_post_trade_quality(
        execution_snapshot=input_execution_snapshot,
        reconciliations=reconciliations,
        cost_estimates=cost_estimates,
        exceptions=exceptions,
        lineage_complete=False,
        receipt_written=False,
    )
    snapshot_id = f"ptsnap_{uuid4().hex[:12]}"
    payload_path = POST_TRADE_NORMALIZED_ROOT / f"{snapshot_id}.json"
    receipt_id = f"receipt_post_trade_{uuid4().hex[:12]}"
    receipt_path = POST_TRADE_RECEIPT_ROOT / f"{receipt_id}.json"
    event_ids = [item.event_id for item in input_execution_snapshot.events]
    lineage = PostTradeLineage(
        source=source,
        input_execution_snapshot_id=input_execution_snapshot.execution_snapshot_id,
        input_execution_receipt_ref=input_execution_snapshot.receipt_ref,
        execution_event_ids=event_ids,
        execution_final_status=input_execution_snapshot.final_status,
        post_trade_status=final_status,
        computed_at_utc=now_utc(),
        output_hash="pending",
        output_ref=str(payload_path),
    )
    quality = build_post_trade_quality(
        execution_snapshot=input_execution_snapshot,
        reconciliations=reconciliations,
        cost_estimates=cost_estimates,
        exceptions=exceptions,
        lineage_complete=True,
        receipt_written=True,
    )
    snapshot = PostTradeSnapshot(
        post_trade_snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        input_execution_snapshot_id=input_execution_snapshot.execution_snapshot_id,
        input_execution_receipt_ref=input_execution_snapshot.receipt_ref,
        final_status=final_status,
        reconciliation_count=len(reconciliations),
        cost_estimate_count=len(cost_estimates),
        exception_count=len(exceptions),
        reconciliations=reconciliations,
        cost_estimates=cost_estimates,
        exceptions=exceptions,
        quality=quality,
        lineage=lineage,
        payload_ref=str(payload_path),
        receipt_ref=str(receipt_path),
        order_creation_allowed=False,
        portfolio_handoff=portfolio_handoff(reconciliations),
        accounting_handoff=accounting_handoff(final_status, context),
        performance_handoff=performance_handoff(
            status=final_status,
            context=context,
            cost_estimates=cost_estimates,
        ),
        review_questions=[
            "Was the execution state classified without creating orders?",
            "Were partial fills, rejects, cancels, and staged-only states preserved?",
            "Were TCA inputs disclosed before any performance handoff?",
        ],
    )
    output_hash = sha256_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    )
    lineage = lineage.model_copy(update={"output_hash": output_hash})
    snapshot = snapshot.model_copy(update={"lineage": lineage})
    receipt = PostTradeReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source": "ExecutionSnapshot",
            "order_creation": "blocked",
            "settlement": "awareness only",
            "accounting": "review handoff only",
            "performance": "paper review only",
        },
        snapshot=snapshot,
        status="ok" if snapshot.quality.ok else "failed",
    )
    write_json(payload_path, snapshot.model_dump(mode="json"))
    write_json(receipt_path, receipt.model_dump(mode="json"))
    return PostTradeBundle(
        source=source,
        input_execution_snapshot=input_execution_snapshot,
        context=context,
        reconciliations=reconciliations,
        cost_estimates=cost_estimates,
        exceptions=exceptions,
        quality=quality,
        lineage=lineage,
        snapshot=snapshot,
        receipt=receipt,
    )


def build_post_trade_bundle_from_execution_snapshot(
    execution_snapshot: ExecutionSnapshot,
    *,
    context: dict[str, Any] | PostTradeContext | None = None,
    source: dict[str, Any] | PostTradeSourceSpec | None = None,
) -> PostTradeBundle:
    post_trade_context = (
        context
        if isinstance(context, PostTradeContext)
        else PostTradeContext.model_validate(context or {})
    )
    post_trade_source = (
        source
        if isinstance(source, PostTradeSourceSpec)
        else PostTradeSourceSpec.model_validate(
            source
            or {
                "config": {
                    "settlement_cycle": post_trade_context.settlement_cycle,
                    "account_ref": post_trade_context.account_ref,
                },
            }
        )
    )
    reconciliations = build_reconciliations(execution_snapshot)
    cost_estimates = build_cost_estimates(
        execution_snapshot=execution_snapshot,
        context=post_trade_context,
        reconciliations=reconciliations,
    )
    exceptions = build_post_trade_exceptions(
        execution_snapshot=execution_snapshot,
        reconciliations=reconciliations,
        cost_estimates=cost_estimates,
    )
    return persist_post_trade_bundle(
        source=post_trade_source,
        input_execution_snapshot=execution_snapshot,
        context=post_trade_context,
        reconciliations=reconciliations,
        cost_estimates=cost_estimates,
        exceptions=exceptions,
    )
