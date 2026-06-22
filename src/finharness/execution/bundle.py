"""Execution quality, persistence, and top-level bundle builder."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.authorization import AuthorizationDecision
from finharness.execution._constants import (
    NAUTILUS_PAPER_ADAPTER_NAME,
    ExecutionStatus,
)
from finharness.execution._util import now_utc, write_json
from finharness.execution.controls import collect_execution_events
from finharness.execution.models import (
    ExecutionAdapter,
    ExecutionBundle,
    ExecutionContext,
    ExecutionEvent,
    ExecutionIntent,
    ExecutionLineage,
    ExecutionOrderRequest,
    ExecutionQuality,
    ExecutionReceipt,
    ExecutionSnapshot,
    ExecutionSourceSpec,
)
from finharness.execution.planning import (
    allowed_decisions,
    authorization_for_execution_context,
    blocked_event,
    build_execution_intents,
    build_order_requests,
)
from finharness.market_data import sha256_text
from finharness.risk_gate import RiskGateSnapshot


def execution_storage_roots() -> tuple[Path, Path]:
    from finharness import execution as execution_package

    return (
        execution_package.EXECUTION_NORMALIZED_ROOT,
        execution_package.EXECUTION_RECEIPT_ROOT,
    )


def final_status(events: list[ExecutionEvent]) -> ExecutionStatus:
    if not events:
        return "not_submitted"
    priority: list[ExecutionStatus] = [
        "blocked_before_submit",
        "rejected",
        "canceled",
        "filled",
        "partially_filled",
        "accepted",
        "submitted_paper",
        "staged",
    ]
    statuses = [item.status for item in events]
    for status in priority:
        if status in statuses:
            return status
    return statuses[-1]


def build_execution_quality(
    *,
    risk_gate_snapshot: RiskGateSnapshot,
    context: ExecutionContext,
    intents: list[ExecutionIntent],
    order_requests: list[ExecutionOrderRequest],
    events: list[ExecutionEvent],
    authorization: AuthorizationDecision | None = None,
    lineage_complete: bool = True,
    receipt_written: bool = True,
) -> ExecutionQuality:
    notes: list[str] = []
    authorization_decision = authorization or authorization_for_execution_context(context)
    risk_gate_lineage_present = bool(
        risk_gate_snapshot.risk_gate_snapshot_id and risk_gate_snapshot.receipt_ref
    )
    allowed_decision_ids = {
        item.decision_id for item in allowed_decisions(risk_gate_snapshot)
    }
    approved_decision_required = bool(intents) and all(
        intent.risk_gate_decision_id in allowed_decision_ids
        for intent in intents
    )
    if not intents:
        approved_decision_required = not bool(allowed_decisions(risk_gate_snapshot))
        notes.append("no approved Risk Gate decisions available for execution")
    paper_mode_required = context.requested_mode in {"dry_run", "paper"}
    live_mode_blocked = (
        context.requested_mode != "live"
        and not context.live_execution_allowed
        and all(request.adapter_mode != "live" for request in order_requests)
    )
    human_review_satisfied_when_required = (
        context.human_review_attested
        or not any(intent.human_review_required for intent in intents)
    )
    idempotency_key_present = all(
        request.idempotency_key and request.client_order_id for request in order_requests
    )
    if not order_requests:
        idempotency_key_present = not intents
    intents_by_id = {intent.intent_id: intent for intent in intents}
    order_request_matches_approved_intent = all(
        request.intent_id in intents_by_id
        and request.symbol == intents_by_id[request.intent_id].symbol
        and request.quantity == intents_by_id[request.intent_id].quantity
        for request in order_requests
    )
    raw_adapter_events_preserved = all(
        bool(item.raw_status) and isinstance(item.raw_event, dict) for item in events
    )
    final_state_present = final_status(events) != "not_submitted" or not intents
    authorization_registered = authorization_decision.allowed
    if not authorization_registered:
        notes.extend(authorization_decision.blocking_reasons)
    ok = (
        risk_gate_lineage_present
        and approved_decision_required
        and paper_mode_required
        and live_mode_blocked
        and authorization_registered
        and human_review_satisfied_when_required
        and idempotency_key_present
        and order_request_matches_approved_intent
        and raw_adapter_events_preserved
        and final_state_present
        and lineage_complete
        and receipt_written
    )
    return ExecutionQuality(
        ok=ok,
        risk_gate_lineage_present=risk_gate_lineage_present,
        approved_decision_required=approved_decision_required,
        paper_mode_required=paper_mode_required,
        live_mode_blocked=live_mode_blocked,
        human_review_satisfied_when_required=human_review_satisfied_when_required,
        idempotency_key_present=idempotency_key_present,
        order_request_matches_approved_intent=order_request_matches_approved_intent,
        raw_adapter_events_preserved=raw_adapter_events_preserved,
        final_state_present=final_state_present,
        authorization_registered=authorization_registered,
        receipt_written=receipt_written,
        notes=notes,
    )


def post_trade_handoff(events: list[ExecutionEvent]) -> list[str]:
    status = final_status(events)
    if status in {"filled", "partially_filled", "canceled", "rejected"}:
        return [f"execution final status {status}; hand off to post-trade review"]
    if status in {"accepted", "submitted_paper", "staged"}:
        return [f"execution status {status}; monitor before post-trade reconciliation"]
    return []


def persist_execution_bundle(
    *,
    source: ExecutionSourceSpec,
    input_risk_gate_snapshot: RiskGateSnapshot,
    context: ExecutionContext,
    intents: list[ExecutionIntent],
    order_requests: list[ExecutionOrderRequest],
    events: list[ExecutionEvent],
    authorization: AuthorizationDecision | None = None,
) -> ExecutionBundle:
    authorization_decision = authorization or authorization_for_execution_context(context)
    quality = build_execution_quality(
        risk_gate_snapshot=input_risk_gate_snapshot,
        context=context,
        intents=intents,
        order_requests=order_requests,
        events=events,
        authorization=authorization_decision,
        lineage_complete=False,
        receipt_written=False,
    )
    snapshot_id = f"exsnap_{uuid4().hex[:12]}"
    normalized_root, receipt_root = execution_storage_roots()
    payload_path = normalized_root / f"{snapshot_id}.json"
    receipt_id = f"receipt_exec_{uuid4().hex[:12]}"
    receipt_path = receipt_root / f"{receipt_id}.json"
    order_request_hash = sha256_text(
        json.dumps(
            [request.model_dump(mode="json") for request in order_requests],
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    lineage = ExecutionLineage(
        source=source,
        input_risk_gate_snapshot_id=input_risk_gate_snapshot.risk_gate_snapshot_id,
        input_risk_gate_receipt_ref=input_risk_gate_snapshot.receipt_ref,
        decision_ids=[intent.risk_gate_decision_id for intent in intents],
        adapter_name=source.adapter_name,
        adapter_mode=context.requested_mode,
        idempotency_keys=[request.idempotency_key for request in order_requests],
        order_request_hash=order_request_hash,
        computed_at_utc=now_utc(),
        output_hash="pending",
        output_ref=str(payload_path),
    )
    quality = build_execution_quality(
        risk_gate_snapshot=input_risk_gate_snapshot,
        context=context,
        intents=intents,
        order_requests=order_requests,
        events=events,
        authorization=authorization_decision,
        lineage_complete=True,
        receipt_written=True,
    )
    snapshot = ExecutionSnapshot(
        execution_snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        input_risk_gate_snapshot_id=input_risk_gate_snapshot.risk_gate_snapshot_id,
        input_risk_gate_receipt_ref=input_risk_gate_snapshot.receipt_ref,
        mode=context.requested_mode,
        intent_count=len(intents),
        order_request_count=len(order_requests),
        event_count=len(events),
        final_status=final_status(events),
        intents=intents,
        order_requests=order_requests,
        events=events,
        authorization=authorization_decision,
        quality=quality,
        lineage=lineage,
        payload_ref=str(payload_path),
        receipt_ref=str(receipt_path),
        execution_allowed=False,
        post_trade_handoff=post_trade_handoff(events),
        review_questions=[
            "Did execution consume only Risk Gate approved decisions?",
            "Were raw adapter events preserved for lifecycle review?",
            "Is live execution still blocked?",
        ],
    )
    output_hash = sha256_text(
        json.dumps(snapshot.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    )
    lineage = lineage.model_copy(update={"output_hash": output_hash})
    snapshot = snapshot.model_copy(update={"lineage": lineage})
    receipt = ExecutionReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source": "RiskGateSnapshot",
            "permission": "paper only",
            "adapter": source.adapter_name,
            "mode": context.requested_mode,
            "authorization": "registered" if authorization_decision.allowed else "blocked",
            "live_execution": "blocked",
        },
        snapshot=snapshot,
        status="ok" if snapshot.quality.ok else "failed",
    )
    write_json(payload_path, snapshot.model_dump(mode="json"))
    write_json(receipt_path, receipt.model_dump(mode="json"))
    return ExecutionBundle(
        source=source,
        input_risk_gate_snapshot=input_risk_gate_snapshot,
        context=context,
        intents=intents,
        order_requests=order_requests,
        events=events,
        quality=quality,
        lineage=lineage,
        snapshot=snapshot,
        receipt=receipt,
    )


def build_execution_bundle_from_risk_gate_snapshot(
    risk_gate_snapshot: RiskGateSnapshot,
    *,
    context: dict[str, Any] | ExecutionContext | None = None,
    source: dict[str, Any] | ExecutionSourceSpec | None = None,
    adapter: ExecutionAdapter | None = None,
) -> ExecutionBundle:
    execution_context = (
        context
        if isinstance(context, ExecutionContext)
        else ExecutionContext.model_validate(context or {})
    )
    authorization_decision = authorization_for_execution_context(execution_context)
    execution_source = (
        source
        if isinstance(source, ExecutionSourceSpec)
        else ExecutionSourceSpec.model_validate(
            source
            or {
                "provider": "NautilusTrader typed paper adapter",
                "method": "paper_order_shape_via_nautilus_model_orders",
                "adapter_name": (
                    NAUTILUS_PAPER_ADAPTER_NAME
                    if execution_context.requested_mode == "paper"
                    else "dry_run"
                ),
                "adapter_mode": execution_context.requested_mode,
                "config": {
                    "operator_execute": execution_context.operator_execute,
                    "live_execution_allowed": execution_context.live_execution_allowed,
                    "operator_id": execution_context.operator_id,
                    "account_id": execution_context.account_id,
                    "authorization_scope": execution_context.authorization_scope,
                    "authorization_registry_ref": (
                        authorization_decision.registry_ref
                    ),
                },
            }
        )
    )
    if execution_context.requested_mode == "live":
        intents: list[ExecutionIntent] = []
        order_requests: list[ExecutionOrderRequest] = []
        events = [blocked_event("live execution is blocked in Layer 9 MVP")]
    else:
        intents = build_execution_intents(
            risk_gate_snapshot=risk_gate_snapshot,
            context=execution_context,
        )
        order_requests = build_order_requests(
            risk_gate_snapshot=risk_gate_snapshot,
            context=execution_context,
            source=execution_source,
            intents=intents,
            authorization_decision=authorization_decision,
        )
        events = collect_execution_events(
            context=execution_context,
            order_requests=order_requests,
            adapter=adapter,
        )
        if not intents:
            events = [blocked_event("no approved Risk Gate decisions available")]
        elif intents and not order_requests:
            reason = (
                "authorization blocked order request: "
                + "; ".join(authorization_decision.blocking_reasons)
                if not authorization_decision.allowed
                else "pre-submit checks blocked order request"
            )
            events = [blocked_event(reason)]
    return persist_execution_bundle(
        source=execution_source,
        input_risk_gate_snapshot=risk_gate_snapshot,
        context=execution_context,
        intents=intents,
        order_requests=order_requests,
        events=events,
        authorization=authorization_decision,
    )
