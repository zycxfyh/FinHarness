"""Pydantic models for hypothesis processing."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.hypotheses._constants import ConfidencePrior, HypothesisStatus
from finharness.interpretation import InterpretationSnapshot


class HypothesisSourceSpec(BaseModel):
    """Source/config layer for hypothesis generation."""

    model_config = ConfigDict(frozen=True)

    provider: str = "FinHarness rule-guided hypotheses"
    method: str = "rule_guided_template"
    input_layer: str = "interpretation"
    template_version: str = "finharness.hypotheses.template.v1"
    llm_provider: str | None = None
    llm_interface: str | None = None
    llm_enabled: bool = False
    hermes_root: str | None = "/root/projects/hermes-agent"
    config: dict[str, Any] = Field(default_factory=dict)


class ValidationCheck(BaseModel):
    """A concrete next-layer validation check."""

    model_config = ConfigDict(frozen=True)

    check_type: Literal[
        "market_reaction",
        "indicator_context",
        "event_follow_up",
        "basket_comparison",
        "human_review",
    ]
    description: str
    required_inputs: list[str]
    expected_support: str
    expected_disconfirm: str


class HypothesisRecord(BaseModel):
    """A falsifiable source-backed research hypothesis."""

    model_config = ConfigDict(frozen=True)

    hypothesis_id: str
    source_interpretation_ids: list[str]
    source_event_ids: list[str]
    symbol: str
    mechanism: str
    hypothesis: str
    horizon: str
    expected_observations: list[str]
    disconfirming_observations: list[str]
    validation_plan: list[ValidationCheck]
    assumptions: list[str]
    confidence_prior: ConfidencePrior
    status: HypothesisStatus
    source_refs: list[str]
    draft_provider: str = "none"
    draft_ref: str | None = None
    created_at_utc: str


class HypothesisQuality(BaseModel):
    """Quality gates for fifth-layer hypotheses."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    record_count: int
    source_backed_hypotheses: bool
    testable_predictions_present: bool
    disconfirming_evidence_present: bool
    horizon_present: bool
    validation_plan_present: bool
    no_execution_language: bool
    no_recommendation_language: bool
    claim_not_marked_validated: bool
    temporal_context_separated: bool
    duplicate_hypothesis_check: bool
    missing_required_fields: dict[str, list[str]] = Field(default_factory=dict)
    blocked_language_hits: dict[str, list[str]] = Field(default_factory=dict)
    duplicate_hypothesis_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HypothesisLineage(BaseModel):
    """Lineage from InterpretationSnapshot into hypothesis output."""

    model_config = ConfigDict(frozen=True)

    source: HypothesisSourceSpec
    input_interpretation_snapshot_id: str
    input_interpretation_receipt_ref: str
    input_event_snapshot_id: str
    interpretation_record_ids: list[str]
    event_record_ids: list[str]
    market_snapshot_refs: list[str] = Field(default_factory=list)
    indicator_snapshot_refs: list[str] = Field(default_factory=list)
    method: str
    model_provider: str | None = None
    prompt_template_version: str | None = None
    computed_at_utc: str
    transform_version: str = "finharness.hypotheses.v1"
    output_hash: str
    output_ref: str


class HypothesisSnapshot(BaseModel):
    """Stable fifth-layer hypothesis evidence for validation workflows."""

    model_config = ConfigDict(frozen=True)

    hypothesis_snapshot_id: str
    as_of_utc: str
    input_interpretation_snapshot_id: str
    universe: list[str]
    record_count: int
    records: list[HypothesisRecord]
    quality: HypothesisQuality
    lineage: HypothesisLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    validation_handoff: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class HypothesisReceipt(BaseModel):
    """Durable evidence root for fifth-layer hypothesis processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "hypothesis_processing"
    stage_flow: dict[str, str]
    snapshot: HypothesisSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class HypothesisBundle(BaseModel):
    """Compact handoff for scripts and graph nodes."""

    model_config = ConfigDict(frozen=True)

    source: HypothesisSourceSpec
    input_interpretation_snapshot: InterpretationSnapshot
    records: list[HypothesisRecord]
    quality: HypothesisQuality
    lineage: HypothesisLineage
    snapshot: HypothesisSnapshot
    receipt: HypothesisReceipt
