"""Execution intent, authorization, and order-request planning."""

from __future__ import annotations

from typing import Literal
from uuid import uuid4

from finharness.authorization import AuthorizationDecision, authorize
from finharness.execution._util import event, now_utc
from finharness.execution.models import (
    ExecutionContext,
    ExecutionEvent,
    ExecutionIntent,
    ExecutionOrderRequest,
    ExecutionSourceSpec,
)
from finharness.market_access_ledger import MarketAccessKey
from finharness.market_data import sha256_text
from finharness.risk_gate import RiskGateDecision, RiskGateSnapshot


def allowed_decisions(snapshot: RiskGateSnapshot) -> list[RiskGateDecision]:
    return [
        decision
        for decision in snapshot.decisions
        if decision.decision == "approved_for_paper_review"
        and decision.paper_review_allowed
        and not decision.live_execution_allowed
    ]


def build_execution_intents(
    *,
    risk_gate_snapshot: RiskGateSnapshot,
    context: ExecutionContext,
) -> list[ExecutionIntent]:
    intents: list[ExecutionIntent] = []
    if not risk_gate_snapshot.quality.ok:
        return intents
    for decision in allowed_decisions(risk_gate_snapshot):
        intents.append(
            ExecutionIntent(
                intent_id=f"exint_{uuid4().hex[:12]}",
                risk_gate_decision_id=decision.decision_id,
                proposal_id=decision.proposal_id,
                symbol=decision.symbol,
                side="paper_review",
                quantity=context.requested_quantity,
                notional_estimate=context.requested_quantity * context.reference_price,
                mode=context.requested_mode,
                human_review_required=decision.human_review_required,
                created_at_utc=now_utc(),
            )
        )
    return intents


def derive_idempotency_key(
    *,
    risk_gate_snapshot: RiskGateSnapshot,
    intent: ExecutionIntent,
    context: ExecutionContext,
) -> str:
    return sha256_text(
        "|".join(
            [
                risk_gate_snapshot.risk_gate_snapshot_id,
                intent.risk_gate_decision_id,
                intent.symbol,
                str(intent.quantity),
                context.order_type,
                context.time_in_force,
                context.requested_mode,
            ]
        )
    )[:32]


def build_order_requests(
    *,
    risk_gate_snapshot: RiskGateSnapshot,
    context: ExecutionContext,
    source: ExecutionSourceSpec,
    intents: list[ExecutionIntent],
    authorization_decision: AuthorizationDecision | None = None,
) -> list[ExecutionOrderRequest]:
    requests: list[ExecutionOrderRequest] = []
    authorization = authorization_decision or authorization_for_execution_context(context)
    if not authorization.allowed:
        return requests
    if context.requested_mode == "live":
        return requests
    if context.requested_quantity <= 0 or context.requested_quantity > context.max_order_quantity:
        return requests
    if not context.human_review_attested:
        return requests
    for intent in intents:
        idempotency_key = derive_idempotency_key(
            risk_gate_snapshot=risk_gate_snapshot,
            intent=intent,
            context=context,
        )
        requests.append(
            ExecutionOrderRequest(
                order_request_id=f"exord_{uuid4().hex[:12]}",
                intent_id=intent.intent_id,
                client_order_id=f"fh-{idempotency_key}",
                symbol=intent.symbol,
                side="buy",
                quantity=intent.quantity,
                order_type=context.order_type,
                time_in_force=context.time_in_force,
                reference_price=context.reference_price,
                adapter_name=source.adapter_name,
                adapter_mode=context.requested_mode,
                idempotency_key=idempotency_key,
                created_at_utc=now_utc(),
            )
        )
    return requests


def stage_events(order_requests: list[ExecutionOrderRequest]) -> list[ExecutionEvent]:
    return [
        event(
            event_type="staged",
            status="staged",
            order_request_id=request.order_request_id,
            quantity=request.quantity,
            raw_status="staged",
            raw_event={"client_order_id": request.client_order_id},
        )
        for request in order_requests
    ]


def blocked_event(reason: str) -> ExecutionEvent:
    return event(
        event_type="blocked",
        status="blocked_before_submit",
        raw_status="blocked_before_submit",
        raw_event={"reason": reason},
    )


def market_access_key_for_order_request(
    *,
    context: ExecutionContext,
    request: ExecutionOrderRequest,
) -> MarketAccessKey:
    return MarketAccessKey(
        environment="live" if context.requested_mode == "live" else "paper",
        venue="paper_review",
        operator=context.operator_id.strip() or context.market_access_operator.strip(),
        account=context.account_id.strip() or context.market_access_account.strip(),
        symbol=request.symbol.upper(),
    )


def authorization_for_execution_context(context: ExecutionContext) -> AuthorizationDecision:
    environment: Literal["paper", "live"] = (
        "live" if context.requested_mode == "live" else context.authorization_environment
    )
    return authorize(
        operator_id=context.operator_id.strip(),
        account_id=context.account_id.strip(),
        environment=environment,
        scope=context.authorization_scope.strip(),
        registry_path=context.authorization_registry_ref,
    )
