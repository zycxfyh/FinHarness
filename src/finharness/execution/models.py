"""Execution data models and adapter protocol."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from finharness.authorization import AuthorizationDecision
from finharness.execution._constants import (
    DEFAULT_PAPER_MARKET_ACCESS_LIMIT,
    NAUTILUS_PAPER_ADAPTER_NAME,
    ExecutionAdapterMode,
    ExecutionEventType,
    ExecutionStatus,
)
from finharness.market_access_ledger import MarketAccessLimit
from finharness.risk_gate import RiskGateSnapshot


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
