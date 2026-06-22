"""Pydantic models for post-trade processing."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.execution import ExecutionSnapshot
from finharness.post_trade._constants import (
    PostTradeExceptionSeverity,
    PostTradeStatus,
)


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
