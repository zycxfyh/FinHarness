"""Post-trade quality, persistence, and top-level bundle builder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.execution import ExecutionSnapshot
from finharness.market_data import sha256_text
from finharness.post_trade._constants import PostTradeStatus
from finharness.post_trade._util import now_utc, write_json
from finharness.post_trade.costs import build_cost_estimates
from finharness.post_trade.exceptions import build_post_trade_exceptions
from finharness.post_trade.models import (
    PostTradeBundle,
    PostTradeContext,
    PostTradeCostEstimate,
    PostTradeException,
    PostTradeLineage,
    PostTradeQuality,
    PostTradeReceipt,
    PostTradeReconciliation,
    PostTradeSnapshot,
    PostTradeSourceSpec,
)
from finharness.post_trade.reconciliation import (
    build_reconciliations,
    final_post_trade_status,
)


def post_trade_storage_roots() -> tuple[Path, Path]:
    from finharness import post_trade as post_trade_package

    return (
        post_trade_package.POST_TRADE_NORMALIZED_ROOT,
        post_trade_package.POST_TRADE_RECEIPT_ROOT,
    )


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
    normalized_root, receipt_root = post_trade_storage_roots()
    payload_path = normalized_root / f"{snapshot_id}.json"
    receipt_id = f"receipt_post_trade_{uuid4().hex[:12]}"
    receipt_path = receipt_root / f"{receipt_id}.json"
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
