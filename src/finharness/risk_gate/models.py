"""Risk-gate data models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.authorization import AuthorizationDecision
from finharness.proposal import ProposalSnapshot
from finharness.restricted_symbols import (
    RestrictedSymbolDecision,
    TradabilityDecision,
    TradabilityProvider,
)
from finharness.risk_gate._constants import RiskGateCheckStatus, RiskGateDecisionValue


class RiskGateSourceSpec(BaseModel):
    """Source/config layer for risk-gate decisions."""

    model_config = ConfigDict(frozen=True)

    provider: str = "FinHarness deterministic risk gate"
    method: str = "rule_guided_risk_gate_mvp"
    input_layer: str = "proposal"
    template_version: str = "finharness.risk_gate.template.v1"
    llm_provider: str | None = None
    llm_interface: str | None = None
    llm_enabled: bool = False
    hermes_root: str | None = "/root/projects/hermes-agent"
    config: dict[str, Any] = Field(default_factory=dict)


class RiskGateContext(BaseModel):
    """Deterministic MVP context for risk checks."""

    model_config = ConfigDict(frozen=True)

    mandate_id: str = "paper_research_mandate_v1"
    mandate_text: str = "Paper research review only; no live execution."
    allowed_symbols: list[str] = Field(
        default_factory=lambda: [
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "NVDA",
            "META",
            "TSLA",
            "SPY",
            "QQQ",
        ]
    )
    allowed_action_types: list[str] = Field(
        default_factory=lambda: [
            "watch_only",
            "research_more",
            "paper_trade_candidate",
            "avoid_or_reject",
        ]
    )
    requested_execution_mode: Literal["none", "paper", "live"] = "paper"
    live_execution_allowed: bool = False
    # Fail-closed: attestation is an action a human takes, never a default.
    human_review_attested: bool = False
    max_paper_notional: float = 1000.0
    requested_notional: float = 100.0
    max_symbol_concentration_pct: float = 0.10
    requested_symbol_concentration_pct: float = 0.02
    liquidity_evidence_present: bool = True
    drawdown_pct: float = 0.0
    hard_stop_drawdown_pct: float = -3.0
    consecutive_losses: int = 0
    hard_stop_consecutive_losses: int = 3
    behavior_reset_required: bool = False
    scenario_review_present: bool = True
    operator_id: str = "paper_operator"
    account_id: str = "paper_account"
    authorization_environment: Literal["paper", "live"] = "paper"
    authorization_scope: str = "risk_review"
    authorization_registry_ref: str | None = None
    restricted_symbols_ref: str | None = None
    tradability_provider: TradabilityProvider = "not_applicable"
    tradability_receipt_ref: str | None = None
    manual_tradability: dict[str, bool] = Field(default_factory=dict)


class RiskGateCheck(BaseModel):
    """One auditable risk-gate check."""

    model_config = ConfigDict(frozen=True)

    check_id: str
    proposal_id: str
    check_type: str
    status: RiskGateCheckStatus
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    blocked_language_hits: list[str] = Field(default_factory=list)
    blocking: bool = False
    created_at_utc: str


class RiskGateDecision(BaseModel):
    """Decision for one ProposalCandidate."""

    model_config = ConfigDict(frozen=True)

    decision_id: str
    proposal_id: str
    symbol: str
    action_type: str
    decision: RiskGateDecisionValue
    checks: list[RiskGateCheck]
    blocking_reasons: list[str]
    required_remediations: list[str]
    authorization: AuthorizationDecision
    restricted_symbol: RestrictedSymbolDecision
    tradability: TradabilityDecision
    paper_review_allowed: bool
    live_execution_allowed: bool = False
    execution_intent: str = "no execution; execution layer is separate"
    sizing_intent: str = "no final sizing; risk gate decision only"
    human_review_required: bool = True
    created_at_utc: str


class RiskGateQuality(BaseModel):
    """Quality gates for risk-gate output."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    candidate_count: int
    decision_count: int
    proposal_snapshot_linked: bool
    proposal_quality_ok: bool
    decision_count_matches_candidate_count: bool
    all_decisions_have_checks: bool
    hard_blocks_enforced: bool
    mandate_present: bool
    permission_boundary_present: bool
    human_review_required: bool
    no_order_language: bool
    no_live_execution_authority: bool
    no_final_sizing: bool
    lineage_complete: bool
    receipt_written: bool
    missing_required_fields: dict[str, list[str]] = Field(default_factory=dict)
    blocked_language_hits: dict[str, list[str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class RiskGateLineage(BaseModel):
    """Lineage from ProposalSnapshot into risk-gate output."""

    model_config = ConfigDict(frozen=True)

    source: RiskGateSourceSpec
    input_proposal_snapshot_id: str
    input_proposal_receipt_ref: str
    proposal_ids: list[str]
    proposal_transform_version: str
    method: str
    model_provider: str | None = None
    prompt_template_version: str | None = None
    computed_at_utc: str
    transform_version: str = "finharness.risk_gate.v1"
    output_hash: str
    output_ref: str


class RiskGateSnapshot(BaseModel):
    """Stable eighth-layer risk-gate evidence."""

    model_config = ConfigDict(frozen=True)

    risk_gate_snapshot_id: str
    as_of_utc: str
    input_proposal_snapshot_id: str
    universe: list[str]
    candidate_count: int
    decision_count: int
    context: RiskGateContext
    decisions: list[RiskGateDecision]
    quality: RiskGateQuality
    lineage: RiskGateLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    execution_handoff: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class RiskGateReceipt(BaseModel):
    """Durable evidence root for eighth-layer risk-gate processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "risk_gate_processing"
    stage_flow: dict[str, str]
    snapshot: RiskGateSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class RiskGateBundle(BaseModel):
    """Compact handoff for scripts and graph nodes."""

    model_config = ConfigDict(frozen=True)

    source: RiskGateSourceSpec
    input_proposal_snapshot: ProposalSnapshot
    context: RiskGateContext
    decisions: list[RiskGateDecision]
    quality: RiskGateQuality
    lineage: RiskGateLineage
    snapshot: RiskGateSnapshot
    receipt: RiskGateReceipt
