"""Pydantic models for proposal processing."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.proposal._constants import ActionType, ProposalStatus
from finharness.validation import ValidationSnapshot


class ProposalSourceSpec(BaseModel):
    """Source/config layer for proposal generation."""

    model_config = ConfigDict(frozen=True)

    provider: str = "FinHarness rule-guided proposal"
    method: str = "rule_guided_proposal_mvp"
    input_layer: str = "validation"
    template_version: str = "finharness.proposal.template.v1"
    llm_provider: str | None = None
    llm_interface: str | None = None
    llm_enabled: bool = False
    hermes_root: str | None = "/root/projects/hermes-agent"
    config: dict[str, Any] = Field(default_factory=dict)


class RiskGateRequest(BaseModel):
    """A request for independent risk-gate review."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    proposal_id: str
    required_checks: list[str]
    risk_budget_request: str
    sizing_intent: str
    execution_intent: str
    human_review_required: bool = True


class ProposalCandidate(BaseModel):
    """A structured action candidate for risk review only."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str
    source_validation_snapshot_id: str
    source_validation_result_ids: list[str]
    source_hypothesis_ids: list[str]
    symbol: str
    action_type: ActionType
    portfolio_role: str
    rationale: str
    evidence_summary: str
    validation_summary: str
    expected_benefit: str
    key_risks: list[str]
    invalidation_triggers: list[str]
    time_horizon: str
    benchmark_context: str
    scenario_notes: list[str]
    constraint_notes: list[str]
    risk_gate_request: RiskGateRequest
    alternatives_considered: list[str]
    do_nothing_case: str
    status: ProposalStatus
    draft_provider: str = "none"
    draft_ref: str | None = None
    created_at_utc: str


class ProposalQuality(BaseModel):
    """Quality gates for proposal output."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    candidate_count: int
    validation_snapshot_linked: bool
    validation_quality_ok: bool
    evidence_summary_present: bool
    validation_summary_present: bool
    portfolio_role_present: bool
    invalidation_triggers_present: bool
    risk_handoff_present: bool
    constraints_present: bool
    alternatives_considered: bool
    do_nothing_case_present: bool
    no_execution_authority: bool
    no_order_language: bool
    no_final_sizing: bool
    human_review_required: bool
    missing_required_fields: dict[str, list[str]] = Field(default_factory=dict)
    blocked_language_hits: dict[str, list[str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ProposalLineage(BaseModel):
    """Lineage from ValidationSnapshot into proposal output."""

    model_config = ConfigDict(frozen=True)

    source: ProposalSourceSpec
    input_validation_snapshot_id: str
    input_validation_receipt_ref: str
    validation_result_ids: list[str]
    hypothesis_ids: list[str]
    validation_transform_version: str
    method: str
    model_provider: str | None = None
    prompt_template_version: str | None = None
    computed_at_utc: str
    transform_version: str = "finharness.proposal.v1"
    output_hash: str
    output_ref: str


class ProposalSnapshot(BaseModel):
    """Stable seventh-layer proposal evidence."""

    model_config = ConfigDict(frozen=True)

    proposal_snapshot_id: str
    as_of_utc: str
    input_validation_snapshot_id: str
    universe: list[str]
    candidate_count: int
    candidates: list[ProposalCandidate]
    quality: ProposalQuality
    lineage: ProposalLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    risk_gate_handoff: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class ProposalReceipt(BaseModel):
    """Durable evidence root for seventh-layer proposal processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "proposal_processing"
    stage_flow: dict[str, str]
    snapshot: ProposalSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class ProposalBundle(BaseModel):
    """Compact handoff for scripts and graph nodes."""

    model_config = ConfigDict(frozen=True)

    source: ProposalSourceSpec
    input_validation_snapshot: ValidationSnapshot
    candidates: list[ProposalCandidate]
    quality: ProposalQuality
    lineage: ProposalLineage
    snapshot: ProposalSnapshot
    receipt: ProposalReceipt
