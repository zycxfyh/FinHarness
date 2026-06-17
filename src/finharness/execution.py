"""Ninth-layer paper execution lifecycle governance.

Execution consumes Risk Gate evidence and produces auditable order-lifecycle
state. It is not strategy generation, not risk override, and not live trading.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import (
    ClientOrderId,
    InstrumentId,
    StrategyId,
    TraderId,
)
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import LimitOrder, MarketOrder
from pydantic import BaseModel, ConfigDict, Field

from finharness.authorization import AuthorizationDecision, authorize
from finharness.effective_ceilings import (
    CeilingResolutionError,
    EnforcedCap,
    enforce_request_limit,
)
from finharness.market_access_ledger import (
    MarketAccessKey,
    MarketAccessLedgerError,
    MarketAccessLimit,
    evaluate_market_access,
    load_market_access_ledger,
    record_consumption,
)
from finharness.market_data import ROOT, sha256_text
from finharness.risk_gate import RiskGateDecision, RiskGateSnapshot

EXECUTION_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "executions"
EXECUTION_RECEIPT_ROOT = ROOT / "data" / "receipts" / "executions"
NAUTILUS_ORDER_BACKEND = "NautilusTrader.model.orders"
NAUTILUS_PAPER_ADAPTER_NAME = "nautilus_paper_order_adapter"
DEFAULT_PAPER_MARKET_ACCESS_LIMIT = MarketAccessLimit(
    max_window_notional=1000.0,
    max_window_order_count=20,
)
PAPER_MARKET_ACCESS_CEILING_FIELD = "paper_market_access_window_notional"

ExecutionAdapterMode = Literal["dry_run", "paper", "live"]
ExecutionStatus = Literal[
    "not_submitted",
    "staged",
    "submitted_paper",
    "accepted",
    "partially_filled",
    "filled",
    "cancel_requested",
    "canceled",
    "rejected",
    "blocked_before_submit",
    "reconciled",
]
ExecutionEventType = Literal[
    "staged",
    "submitted",
    "accepted",
    "partial_fill",
    "fill",
    "cancel_requested",
    "canceled",
    "rejected",
    "blocked",
    "reconciled",
]


class ExecutionSourceSpec(BaseModel):
    """Source/config layer for execution processing."""

    model_config = ConfigDict(frozen=True)

    provider: str = "FinHarness deterministic execution"
    method: str = "paper_execution_lifecycle_mvp"
    input_layer: str = "risk_gate"
    template_version: str = "finharness.execution.template.v1"
    adapter_name: str = NAUTILUS_PAPER_ADAPTER_NAME
    adapter_mode: ExecutionAdapterMode = "dry_run"
    config: dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(BaseModel):
    """Permission and order-shaping context for execution MVP."""

    model_config = ConfigDict(frozen=True)

    mandate_id: str = "paper_execution_mandate_v1"
    requested_mode: ExecutionAdapterMode = "dry_run"
    operator_execute: bool = False
    live_execution_allowed: bool = False
    # Fail-closed: attestation is an action a human takes, never a default.
    human_review_attested: bool = False
    order_type: Literal["market", "limit"] = "market"
    time_in_force: Literal["day", "gtc"] = "day"
    requested_quantity: int = 1
    max_order_quantity: int = 10
    reference_price: float = 100.0
    routing_policy: str = "paper adapter; no smart routing"
    allow_fractional: bool = False
    cancel_after_submit: bool = False
    operator_id: str = "paper_operator"
    account_id: str = "paper_account"
    authorization_environment: Literal["paper", "live"] = "paper"
    authorization_scope: str = "paper_execution"
    authorization_registry_ref: str | None = None
    market_access_operator: str = "paper_operator"
    market_access_account: str = "paper_account"
    market_access_limit: MarketAccessLimit | None = Field(
        default_factory=lambda: DEFAULT_PAPER_MARKET_ACCESS_LIMIT
    )
    market_access_ceiling_rule_root: str | None = None
    market_access_ceiling_certification_root: str | None = None


class ExecutionIntent(BaseModel):
    """Approved Risk Gate decision translated into execution intent."""

    model_config = ConfigDict(frozen=True)

    intent_id: str
    risk_gate_decision_id: str
    proposal_id: str
    symbol: str
    side: Literal["paper_buy_review", "paper_sell_review", "paper_review"]
    quantity: int
    notional_estimate: float
    mode: ExecutionAdapterMode
    human_review_required: bool
    created_at_utc: str


class ExecutionOrderRequest(BaseModel):
    """Order-shaped request before adapter submission."""

    model_config = ConfigDict(frozen=True)

    order_request_id: str
    intent_id: str
    client_order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    order_type: Literal["market", "limit"]
    time_in_force: Literal["day", "gtc"]
    reference_price: float
    adapter_name: str
    adapter_mode: ExecutionAdapterMode
    idempotency_key: str
    created_at_utc: str


class ExecutionEvent(BaseModel):
    """Normalized lifecycle event plus raw adapter detail."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    order_request_id: str | None = None
    event_type: ExecutionEventType
    status: ExecutionStatus
    quantity: int = 0
    filled_quantity: int = 0
    average_price: float | None = None
    raw_status: str
    raw_event: dict[str, Any] = Field(default_factory=dict)
    created_at_utc: str


class ExecutionQuality(BaseModel):
    """Quality gates for execution output."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    risk_gate_lineage_present: bool
    approved_decision_required: bool
    paper_mode_required: bool
    live_mode_blocked: bool
    human_review_satisfied_when_required: bool
    idempotency_key_present: bool
    order_request_matches_approved_intent: bool
    raw_adapter_events_preserved: bool
    final_state_present: bool
    authorization_registered: bool
    receipt_written: bool
    notes: list[str] = Field(default_factory=list)


class ExecutionLineage(BaseModel):
    """Lineage from RiskGateSnapshot into execution output."""

    model_config = ConfigDict(frozen=True)

    source: ExecutionSourceSpec
    input_risk_gate_snapshot_id: str
    input_risk_gate_receipt_ref: str
    decision_ids: list[str]
    adapter_name: str
    adapter_mode: ExecutionAdapterMode
    idempotency_keys: list[str]
    order_request_hash: str
    computed_at_utc: str
    transform_version: str = "finharness.execution.v1"
    output_hash: str
    output_ref: str


class ExecutionSnapshot(BaseModel):
    """Stable ninth-layer execution evidence."""

    model_config = ConfigDict(frozen=True)

    execution_snapshot_id: str
    as_of_utc: str
    input_risk_gate_snapshot_id: str
    input_risk_gate_receipt_ref: str
    mode: ExecutionAdapterMode
    intent_count: int
    order_request_count: int
    event_count: int
    final_status: ExecutionStatus
    intents: list[ExecutionIntent]
    order_requests: list[ExecutionOrderRequest]
    events: list[ExecutionEvent]
    authorization: AuthorizationDecision
    quality: ExecutionQuality
    lineage: ExecutionLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    post_trade_handoff: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class ExecutionReceipt(BaseModel):
    """Durable evidence root for ninth-layer execution processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "execution_processing"
    stage_flow: dict[str, str]
    snapshot: ExecutionSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class ExecutionBundle(BaseModel):
    """Compact handoff for scripts and graph nodes."""

    model_config = ConfigDict(frozen=True)

    source: ExecutionSourceSpec
    input_risk_gate_snapshot: RiskGateSnapshot
    context: ExecutionContext
    intents: list[ExecutionIntent]
    order_requests: list[ExecutionOrderRequest]
    events: list[ExecutionEvent]
    quality: ExecutionQuality
    lineage: ExecutionLineage
    snapshot: ExecutionSnapshot
    receipt: ExecutionReceipt


class ExecutionAdapter(Protocol):
    """Small adapter boundary for deterministic tests and future paper brokers."""

    adapter_name: str
    adapter_mode: ExecutionAdapterMode

    def submit(self, request: ExecutionOrderRequest) -> list[ExecutionEvent]:
        """Submit an order request and return normalized lifecycle events."""

    def cancel(self, request: ExecutionOrderRequest) -> list[ExecutionEvent]:
        """Cancel an order request and return normalized lifecycle events."""


class FakePaperExecutionAdapter:
    """Deterministic paper adapter; never talks to a real broker."""

    adapter_name = "fake_paper_adapter"
    adapter_mode: ExecutionAdapterMode = "paper"

    def __init__(self, *, fill_mode: Literal["accepted", "partial", "filled", "reject"]):
        self.fill_mode = fill_mode
        self.submitted_keys: set[str] = set()

    def submit(self, request: ExecutionOrderRequest) -> list[ExecutionEvent]:
        if request.idempotency_key in self.submitted_keys:
            return [
                event(
                    event_type="rejected",
                    status="rejected",
                    order_request_id=request.order_request_id,
                    raw_status="duplicate_client_order_id",
                    raw_event={"idempotency_key": request.idempotency_key},
                )
            ]
        self.submitted_keys.add(request.idempotency_key)
        submitted = event(
            event_type="submitted",
            status="submitted_paper",
            order_request_id=request.order_request_id,
            quantity=request.quantity,
            raw_status="submitted_paper",
            raw_event={"client_order_id": request.client_order_id},
        )
        if self.fill_mode == "reject":
            return [
                submitted,
                event(
                    event_type="rejected",
                    status="rejected",
                    order_request_id=request.order_request_id,
                    quantity=request.quantity,
                    raw_status="rejected",
                    raw_event={"reason": "fake adapter configured rejection"},
                ),
            ]
        if self.fill_mode == "partial":
            return [
                submitted,
                event(
                    event_type="partial_fill",
                    status="partially_filled",
                    order_request_id=request.order_request_id,
                    quantity=request.quantity,
                    filled_quantity=max(1, request.quantity // 2),
                    average_price=request.reference_price,
                    raw_status="partially_filled",
                    raw_event={"fill_mode": self.fill_mode},
                ),
            ]
        if self.fill_mode == "filled":
            return [
                submitted,
                event(
                    event_type="fill",
                    status="filled",
                    order_request_id=request.order_request_id,
                    quantity=request.quantity,
                    filled_quantity=request.quantity,
                    average_price=request.reference_price,
                    raw_status="filled",
                    raw_event={"fill_mode": self.fill_mode},
                ),
            ]
        return [
            submitted,
            event(
                event_type="accepted",
                status="accepted",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="accepted",
                raw_event={"fill_mode": self.fill_mode},
            ),
        ]

    def cancel(self, request: ExecutionOrderRequest) -> list[ExecutionEvent]:
        return [
            event(
                event_type="cancel_requested",
                status="cancel_requested",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="pending_cancel",
                raw_event={"client_order_id": request.client_order_id},
            ),
            event(
                event_type="canceled",
                status="canceled",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="canceled",
                raw_event={"client_order_id": request.client_order_id},
            ),
        ]


class NautilusPaperExecutionAdapter:
    """Paper adapter that delegates order-shape semantics to NautilusTrader.

    It does not route to a broker, simulate fills, or authorize live execution.
    The adapter only converts a FinHarness order request into a Nautilus typed
    order and records the resulting order evidence.
    """

    adapter_name = NAUTILUS_PAPER_ADAPTER_NAME
    adapter_mode: ExecutionAdapterMode = "paper"

    def __init__(
        self,
        *,
        trader_id: str = "FINHARNESS-001",
        strategy_id: str = "L9-PAPER",
        venue: str = "FINHARNESS",
    ) -> None:
        self.trader_id = TraderId(trader_id)
        self.strategy_id = StrategyId(strategy_id)
        self.venue = venue

    def submit(self, request: ExecutionOrderRequest) -> list[ExecutionEvent]:
        order = self._build_order(request)
        raw_order = order.to_dict()
        return [
            event(
                event_type="submitted",
                status="submitted_paper",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="nautilus_order_initialized",
                raw_event={
                    "backend": NAUTILUS_ORDER_BACKEND,
                    "adapter_name": self.adapter_name,
                    "order": raw_order,
                },
            ),
            event(
                event_type="accepted",
                status="accepted",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="nautilus_paper_accepted",
                raw_event={
                    "backend": NAUTILUS_ORDER_BACKEND,
                    "adapter_name": self.adapter_name,
                    "order_type": raw_order.get("type"),
                    "order_status": raw_order.get("status"),
                    "client_order_id": raw_order.get("client_order_id"),
                    "execution_allowed": False,
                },
            ),
        ]

    def cancel(self, request: ExecutionOrderRequest) -> list[ExecutionEvent]:
        return [
            event(
                event_type="cancel_requested",
                status="cancel_requested",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="nautilus_paper_cancel_requested",
                raw_event={
                    "backend": NAUTILUS_ORDER_BACKEND,
                    "adapter_name": self.adapter_name,
                    "client_order_id": request.client_order_id,
                },
            ),
            event(
                event_type="canceled",
                status="canceled",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="nautilus_paper_canceled",
                raw_event={
                    "backend": NAUTILUS_ORDER_BACKEND,
                    "adapter_name": self.adapter_name,
                    "client_order_id": request.client_order_id,
                },
            ),
        ]

    def _build_order(self, request: ExecutionOrderRequest) -> MarketOrder | LimitOrder:
        instrument_id = InstrumentId.from_str(f"{request.symbol}.{self.venue}")
        client_order_id = ClientOrderId(request.client_order_id)
        order_side = OrderSide.BUY if request.side == "buy" else OrderSide.SELL
        time_in_force = TimeInForce.DAY if request.time_in_force == "day" else TimeInForce.GTC
        quantity = Quantity.from_int(request.quantity)
        common = {
            "trader_id": self.trader_id,
            "strategy_id": self.strategy_id,
            "instrument_id": instrument_id,
            "client_order_id": client_order_id,
            "order_side": order_side,
            "quantity": quantity,
            "init_id": UUID4(),
            "ts_init": int(datetime.now(UTC).timestamp() * 1_000_000_000),
            "time_in_force": time_in_force,
        }
        if request.order_type == "limit":
            return LimitOrder(
                **common,
                price=Price.from_str(f"{request.reference_price:.8f}"),
            )
        return MarketOrder(**common)


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def event(
    *,
    event_type: ExecutionEventType,
    status: ExecutionStatus,
    raw_status: str,
    order_request_id: str | None = None,
    quantity: int = 0,
    filled_quantity: int = 0,
    average_price: float | None = None,
    raw_event: dict[str, Any] | None = None,
) -> ExecutionEvent:
    return ExecutionEvent(
        event_id=f"exevt_{uuid4().hex[:12]}",
        order_request_id=order_request_id,
        event_type=event_type,
        status=status,
        quantity=quantity,
        filled_quantity=filled_quantity,
        average_price=average_price,
        raw_status=raw_status,
        raw_event=raw_event or {},
        created_at_utc=now_utc(),
    )


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


def market_access_limit_for_execution_context(
    context: ExecutionContext,
) -> tuple[MarketAccessLimit, EnforcedCap]:
    requested_notional = (
        context.market_access_limit.max_window_notional
        if context.market_access_limit is not None
        else None
    )
    cap = enforce_request_limit(
        field=PAPER_MARKET_ACCESS_CEILING_FIELD,
        default_ceiling=DEFAULT_PAPER_MARKET_ACCESS_LIMIT.max_window_notional,
        request_limit=requested_notional,
        rule_change_root=Path(context.market_access_ceiling_rule_root)
        if context.market_access_ceiling_rule_root
        else None,
        certification_root=Path(context.market_access_ceiling_certification_root)
        if context.market_access_ceiling_certification_root
        else None,
    )
    requested_count = (
        context.market_access_limit.max_window_order_count
        if context.market_access_limit is not None
        else DEFAULT_PAPER_MARKET_ACCESS_LIMIT.max_window_order_count
    )
    return (
        MarketAccessLimit(
            max_window_notional=cap.enforced_cap,
            max_window_order_count=min(
                requested_count,
                DEFAULT_PAPER_MARKET_ACCESS_LIMIT.max_window_order_count,
            ),
        ),
        cap,
    )


def collect_execution_events(
    *,
    context: ExecutionContext,
    order_requests: list[ExecutionOrderRequest],
    adapter: ExecutionAdapter | None = None,
) -> list[ExecutionEvent]:
    if not order_requests:
        return []
    events = stage_events(order_requests)
    if not context.operator_execute or context.requested_mode == "dry_run":
        return events
    if context.requested_mode == "live":
        events.append(blocked_event("live execution is blocked in Layer 9 MVP"))
        return events
    paper_adapter = adapter or NautilusPaperExecutionAdapter()
    for request in order_requests:
        notional = request.quantity * request.reference_price
        try:
            effective_market_access_limit, market_access_cap = (
                market_access_limit_for_execution_context(context)
            )
        except CeilingResolutionError as exc:
            events.append(
                blocked_event(
                    "market-access notional ceiling could not be resolved; "
                    f"refusing fail-closed: {exc}"
                )
            )
            continue
        try:
            market_access = evaluate_market_access(
                key=market_access_key_for_order_request(
                    context=context,
                    request=request,
                ),
                notional=notional,
                limit=effective_market_access_limit,
                ledger=load_market_access_ledger(),
                limit_evidence=market_access_cap.as_receipt_dict(),
            )
        except MarketAccessLedgerError as exc:
            events.append(
                blocked_event(
                    "market-access ledger unreadable; refusing fail-closed: "
                    f"{exc}"
                )
            )
            continue
        if not market_access.allowed_within_limit:
            events.append(
                blocked_event(
                    "market-access ledger blocked order request: "
                    + "; ".join(market_access.blocking_reasons)
                )
            )
            continue
        try:
            record_consumption(
                key=market_access_key_for_order_request(
                    context=context,
                    request=request,
                ),
                notional=notional,
                limit=effective_market_access_limit,
                limit_evidence=market_access_cap.as_receipt_dict(),
                source_ref=request.order_request_id,
            )
        except MarketAccessLedgerError as exc:
            events.append(
                blocked_event(
                    "market-access ledger consumption failed before paper submit: "
                    f"{exc}"
                )
            )
            continue
        events.extend(paper_adapter.submit(request))
        if context.cancel_after_submit:
            events.extend(paper_adapter.cancel(request))
    return events


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
    payload_path = EXECUTION_NORMALIZED_ROOT / f"{snapshot_id}.json"
    receipt_id = f"receipt_exec_{uuid4().hex[:12]}"
    receipt_path = EXECUTION_RECEIPT_ROOT / f"{receipt_id}.json"
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
