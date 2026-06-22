"""Validation data models and provider protocols."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from finharness.hypotheses import HypothesisRecord, HypothesisSnapshot
from finharness.validation._constants import ValidationCheckType, ValidationResult


class ValidationSourceSpec(BaseModel):
    """Source/config layer for validation runs."""

    model_config = ConfigDict(frozen=True)

    provider: str = "FinHarness rule-guided validation"
    method: str = "rule_guided_validation_mvp"
    input_layer: str = "hypotheses"
    template_version: str = "finharness.validation.template.v1"
    llm_provider: str | None = None
    llm_interface: str | None = None
    llm_enabled: bool = False
    hermes_root: str | None = "/root/projects/hermes-agent"
    config: dict[str, Any] = Field(default_factory=dict)


class ValidationJob(BaseModel):
    """A validation job created from one hypothesis."""

    model_config = ConfigDict(frozen=True)

    validation_job_id: str
    hypothesis_id: str
    symbol: str
    planned_check_types: list[str]
    disconfirmation_items: list[str]
    required_inputs: list[str]
    created_at_utc: str


class ValidationCheckResult(BaseModel):
    """A single validation check result."""

    model_config = ConfigDict(frozen=True)

    check_id: str
    validation_job_id: str
    hypothesis_id: str
    check_type: ValidationCheckType
    input_refs: list[str]
    method: str
    window: str
    metrics: dict[str, Any]
    result: ValidationResult
    supports_hypothesis: bool
    disconfirms_hypothesis: bool
    confidence: Literal["low", "medium", "high", "unknown"]
    limitations: list[str]
    created_at_utc: str


class BacktestEvidence(BaseModel):
    """Provider-shaped backtest evidence before it becomes a validation result."""

    model_config = ConfigDict(frozen=True)

    method: str
    window: str
    metrics: dict[str, Any]
    result: ValidationResult
    supports_hypothesis: bool
    disconfirms_hypothesis: bool
    limitations: list[str]

class ValidationDraftProvider(Protocol):
    """Optional provider interface for future LLM validation commentary."""

    provider_name: str

    def assess(self, hypothesis: HypothesisRecord) -> dict[str, Any]:
        """Return optional draft assessment fields for validation."""

class BacktestEvidenceProvider(Protocol):
    """Optional provider interface for research backtest evidence."""

    provider_name: str

    def assess(
        self,
        *,
        job: ValidationJob,
        hypothesis: HypothesisRecord,
        snapshot: HypothesisSnapshot,
    ) -> BacktestEvidence:
        """Return one conservative backtest evidence object for a job."""

class ValidationQuality(BaseModel):
    """Quality gates for validation output."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    job_count: int
    result_count: int
    hypothesis_source_linked: bool
    validation_jobs_created: bool
    source_validity_checked: bool
    at_least_one_market_check: bool
    at_least_one_disconfirmation_check: bool
    benchmark_context_present: bool
    no_proposal_or_execution_language: bool
    limitations_present: bool
    result_not_overclaimed: bool
    lineage_complete: bool
    missing_required_fields: dict[str, list[str]] = Field(default_factory=dict)
    blocked_language_hits: dict[str, list[str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ValidationLineage(BaseModel):
    """Lineage from HypothesisSnapshot into validation output."""

    model_config = ConfigDict(frozen=True)

    source: ValidationSourceSpec
    input_hypothesis_snapshot_id: str
    input_hypothesis_receipt_ref: str
    hypothesis_ids: list[str]
    interpretation_snapshot_id: str
    event_snapshot_id: str
    market_snapshot_refs: list[str] = Field(default_factory=list)
    indicator_snapshot_refs: list[str] = Field(default_factory=list)
    method: str
    model_provider: str | None = None
    prompt_template_version: str | None = None
    computed_at_utc: str
    transform_version: str = "finharness.validation.v1"
    output_hash: str
    output_ref: str


class ValidationSnapshot(BaseModel):
    """Stable sixth-layer validation evidence."""

    model_config = ConfigDict(frozen=True)

    validation_snapshot_id: str
    as_of_utc: str
    input_hypothesis_snapshot_id: str
    universe: list[str]
    job_count: int
    result_count: int
    jobs: list[ValidationJob]
    results: list[ValidationCheckResult]
    quality: ValidationQuality
    lineage: ValidationLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    proposal_handoff: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class ValidationReceipt(BaseModel):
    """Durable evidence root for sixth-layer validation processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "validation_processing"
    stage_flow: dict[str, str]
    snapshot: ValidationSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class ValidationBundle(BaseModel):
    """Compact handoff for scripts and graph nodes."""

    model_config = ConfigDict(frozen=True)

    source: ValidationSourceSpec
    input_hypothesis_snapshot: HypothesisSnapshot
    jobs: list[ValidationJob]
    results: list[ValidationCheckResult]
    quality: ValidationQuality
    lineage: ValidationLineage
    snapshot: ValidationSnapshot
    receipt: ValidationReceipt
