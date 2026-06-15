"""Sixth-layer validation governance.

Validation tests fifth-layer hypotheses against source validity, mechanism,
benchmark context, planned checks, and disconfirming observations. It does not
create proposals, recommendations, or execution permission.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from finharness.hypotheses import HypothesisRecord, HypothesisSnapshot
from finharness.market_data import ROOT, display_path, sha256_text
from finharness.validation_metrics import assess_realized_move, load_cached_close_series
from finharness.vectorbt_runner import VECTORBT_BACKEND, run_vectorbt_moving_average_research

VALIDATION_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "validations"
VALIDATION_RECEIPT_ROOT = ROOT / "data" / "receipts" / "validations"

ValidationResult = Literal[
    "supported",
    "weakened",
    "disconfirmed",
    "inconclusive",
    "not_testable",
]

ValidationCheckType = Literal[
    "source_validity",
    "mechanism",
    "event_reaction",
    "benchmark_context",
    "disconfirmation",
    "limitations",
    "backtest",
]

BACKTEST_LIMITATIONS = [
    "Single MA-crossover screen; in-sample; costs/slippage only as parameterized; "
    "historical, not predictive; evidence only, not an execution signal.",
]

BLOCKED_VALIDATION_LANGUAGE = [
    r"\bbuy\b(?!-side)",
    r"\bsell\b(?!-side)",
    r"\bhold\b",
    r"\bshort\b(?!-term|-run|-dated|-horizon)",
    r"\blong\b(?!-term|-run|-dated|-horizon)",
    r"\btarget price\b",
    r"\bprice target\b",
    r"\bplace order\b",
    r"\bexecute\b",
    r"\bready to trade\b",
    r"\btrade recommendation\b",
    r"\bvalidated alpha\b",
    r"\bguaranteed\b",
    "买入",
    "卖出",
    "持有",
    "做多",
    "做空",
    "目标价",
    "下单",
    "执行",
    "已验证alpha",
    "保证",
]


class ValidationDraftProvider(Protocol):
    """Optional provider interface for future LLM validation commentary."""

    provider_name: str

    def assess(self, hypothesis: HypothesisRecord) -> dict[str, Any]:
        """Return optional draft assessment fields for validation."""


class NullValidationDraftProvider:
    """Default provider: deterministic validation, no LLM call."""

    provider_name = "none"

    def assess(self, hypothesis: HypothesisRecord) -> dict[str, Any]:
        return {}


class HermesValidationDraftProvider:
    """Reserved adapter boundary for /root/projects/hermes-agent."""

    provider_name = "hermes-agent"

    def __init__(self, *, hermes_root: str | Path = "/root/projects/hermes-agent") -> None:
        self.hermes_root = Path(hermes_root)

    def assess(self, hypothesis: HypothesisRecord) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "enabled": False,
            "hermes_root": str(self.hermes_root),
            "note": "LLM validation interface reserved; deterministic checks used in MVP.",
            "hypothesis_id": hypothesis.hypothesis_id,
        }


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


class NullBacktestEvidenceProvider:
    """Default provider: no backtest is run in deterministic offline validation."""

    provider_name = "none"

    def assess(
        self,
        *,
        job: ValidationJob,
        hypothesis: HypothesisRecord,
        snapshot: HypothesisSnapshot,
    ) -> BacktestEvidence:
        return BacktestEvidence(
            method=VECTORBT_BACKEND,
            window="not_available",
            metrics=backtest_metrics(
                fast=None,
                slow=None,
                initial_cash=None,
                fees=None,
                slippage=None,
                start_value=None,
                end_value=None,
                total_return=None,
                trade_count=0,
                provider=self.provider_name,
                reason="no backtest provider configured",
            ),
            result="not_testable",
            supports_hypothesis=False,
            disconfirms_hypothesis=False,
            limitations=[
                *BACKTEST_LIMITATIONS,
                "No backtest provider was configured for this validation run.",
            ],
        )


class VectorbtBacktestEvidenceProvider:
    """vectorbt-backed validation evidence adapter.

    The provider owns only research evidence shaping. It does not create
    proposals, orders, position sizing, or execution permission.
    """

    provider_name = "vectorbt"

    def __init__(
        self,
        *,
        history_by_symbol: dict[str, Any],
        fast: int = 20,
        slow: int = 50,
        initial_cash: float = 10_000.0,
        fees: float = 0.0,
        slippage: float = 0.0,
    ) -> None:
        self.history_by_symbol = {
            symbol.upper(): history for symbol, history in history_by_symbol.items()
        }
        self.fast = fast
        self.slow = slow
        self.initial_cash = initial_cash
        self.fees = fees
        self.slippage = slippage

    def assess(
        self,
        *,
        job: ValidationJob,
        hypothesis: HypothesisRecord,
        snapshot: HypothesisSnapshot,
    ) -> BacktestEvidence:
        history = self.history_by_symbol.get(hypothesis.symbol.upper())
        if history is None:
            return self._not_testable(
                window="not_available",
                reason=f"no history configured for {hypothesis.symbol.upper()}",
            )

        window = backtest_window(history)
        try:
            summary = run_vectorbt_moving_average_research(
                history,
                fast=self.fast,
                slow=self.slow,
                initial_cash=self.initial_cash,
                fees=self.fees,
                slippage=self.slippage,
            )
        except Exception as exc:  # vectorbt screens degrade to evidence, not workflow failure.
            return self._not_testable(window=window, reason=str(exc))

        metrics = backtest_metrics(
            fast=self.fast,
            slow=self.slow,
            initial_cash=self.initial_cash,
            fees=self.fees,
            slippage=self.slippage,
            start_value=summary.start_value,
            end_value=summary.end_value,
            total_return=summary.total_return,
            trade_count=summary.trade_count,
            provider=self.provider_name,
            strategy=summary.strategy,
        )
        result = map_backtest_result(
            trade_count=summary.trade_count,
            total_return=summary.total_return,
        )
        return BacktestEvidence(
            method=summary.backend,
            window=window,
            metrics=metrics,
            result=result,
            supports_hypothesis=result == "supported",
            disconfirms_hypothesis=result == "weakened",
            limitations=BACKTEST_LIMITATIONS,
        )

    def _not_testable(self, *, window: str, reason: str) -> BacktestEvidence:
        return BacktestEvidence(
            method=VECTORBT_BACKEND,
            window=window,
            metrics=backtest_metrics(
                fast=self.fast,
                slow=self.slow,
                initial_cash=self.initial_cash,
                fees=self.fees,
                slippage=self.slippage,
                start_value=None,
                end_value=None,
                total_return=None,
                trade_count=0,
                provider=self.provider_name,
                reason=reason,
            ),
            result="not_testable",
            supports_hypothesis=False,
            disconfirms_hypothesis=False,
            limitations=[*BACKTEST_LIMITATIONS, reason],
        )


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


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def find_blocked_language(value: str) -> list[str]:
    lower = value.lower()
    hits: list[str] = []
    for pattern in BLOCKED_VALIDATION_LANGUAGE:
        if re.search(pattern, lower):
            hits.append(pattern)
    return hits


def result_text_for_guard(result: ValidationCheckResult) -> str:
    return "\n".join(
        [
            result.method,
            result.window,
            str(result.metrics),
            *result.limitations,
        ]
    )


def create_validation_jobs(snapshot: HypothesisSnapshot) -> list[ValidationJob]:
    jobs: list[ValidationJob] = []
    for record in snapshot.records:
        required_inputs = sorted(
            {
                required
                for check in record.validation_plan
                for required in check.required_inputs
            }
        )
        jobs.append(
            ValidationJob(
                validation_job_id=f"valjob_{uuid4().hex[:12]}",
                hypothesis_id=record.hypothesis_id,
                symbol=record.symbol,
                planned_check_types=[check.check_type for check in record.validation_plan],
                disconfirmation_items=record.disconfirming_observations,
                required_inputs=required_inputs,
                created_at_utc=now_utc(),
            )
        )
    return jobs


def backtest_input_refs(snapshot: HypothesisSnapshot) -> list[str]:
    return [
        *snapshot.lineage.market_snapshot_refs,
        *snapshot.lineage.indicator_snapshot_refs,
    ]


def backtest_metrics(
    *,
    fast: int | None,
    slow: int | None,
    initial_cash: float | None,
    fees: float | None,
    slippage: float | None,
    start_value: float | None,
    end_value: float | None,
    total_return: float | None,
    trade_count: int,
    provider: str,
    reason: str | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "fast": fast,
        "slow": slow,
        "initial_cash": initial_cash,
        "fees": fees,
        "slippage": slippage,
        "start_value": start_value,
        "end_value": end_value,
        "total_return": total_return,
        "trade_count": trade_count,
        "provider": provider,
    }
    if reason:
        metrics["reason"] = reason
    if strategy:
        metrics["strategy"] = strategy
    return metrics


def backtest_window(history: Any) -> str:
    if isinstance(history, pd.DataFrame) and not history.empty and "date" in history.columns:
        dates = pd.to_datetime(history["date"], errors="coerce", utc=True).dropna()
        if not dates.empty:
            return f"{dates.min().date().isoformat()} to {dates.max().date().isoformat()}"
    try:
        return f"{len(history)} rows"
    except TypeError:
        return "unknown_window"


def map_backtest_result(*, trade_count: int, total_return: float) -> ValidationResult:
    if trade_count == 0:
        return "not_testable"
    if total_return >= 0.02:
        return "supported"
    if total_return <= -0.02:
        return "weakened"
    return "inconclusive"


def backtest_evidence_result(
    *,
    job: ValidationJob,
    hypothesis: HypothesisRecord,
    snapshot: HypothesisSnapshot,
    provider: BacktestEvidenceProvider,
) -> ValidationCheckResult:
    try:
        evidence = provider.assess(job=job, hypothesis=hypothesis, snapshot=snapshot)
    except Exception as exc:  # provider failures become not-testable evidence.
        evidence = BacktestEvidence(
            method=VECTORBT_BACKEND,
            window="not_available",
            metrics=backtest_metrics(
                fast=None,
                slow=None,
                initial_cash=None,
                fees=None,
                slippage=None,
                start_value=None,
                end_value=None,
                total_return=None,
                trade_count=0,
                provider=getattr(provider, "provider_name", "unknown"),
                reason=str(exc),
            ),
            result="not_testable",
            supports_hypothesis=False,
            disconfirms_hypothesis=False,
            limitations=[*BACKTEST_LIMITATIONS, str(exc)],
        )

    return ValidationCheckResult(
        check_id=f"valchk_{uuid4().hex[:12]}",
        validation_job_id=job.validation_job_id,
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="backtest",
        input_refs=backtest_input_refs(snapshot),
        method=evidence.method,
        window=evidence.window,
        metrics=evidence.metrics,
        result=evidence.result,
        supports_hypothesis=evidence.supports_hypothesis,
        disconfirms_hypothesis=evidence.disconfirms_hypothesis,
        confidence="low",
        limitations=evidence.limitations,
        created_at_utc=now_utc(),
    )


def source_validity_result(
    *,
    job: ValidationJob,
    hypothesis: HypothesisRecord,
) -> ValidationCheckResult:
    linked = bool(
        hypothesis.source_interpretation_ids
        and hypothesis.source_event_ids
        and hypothesis.source_refs
    )
    return ValidationCheckResult(
        check_id=f"valchk_{uuid4().hex[:12]}",
        validation_job_id=job.validation_job_id,
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="source_validity",
        input_refs=hypothesis.source_refs,
        method="source_ref_presence_check",
        window=hypothesis.horizon,
        metrics={
            "source_interpretation_count": len(hypothesis.source_interpretation_ids),
            "source_event_count": len(hypothesis.source_event_ids),
            "source_ref_count": len(hypothesis.source_refs),
        },
        result="supported" if linked else "not_testable",
        supports_hypothesis=linked,
        disconfirms_hypothesis=False,
        confidence="medium" if linked else "low",
        limitations=[
            "Source-link presence does not prove source content is economically material.",
        ],
        created_at_utc=now_utc(),
    )


def mechanism_result(
    *,
    job: ValidationJob,
    hypothesis: HypothesisRecord,
) -> ValidationCheckResult:
    mechanism_present = bool(hypothesis.mechanism and hypothesis.assumptions)
    return ValidationCheckResult(
        check_id=f"valchk_{uuid4().hex[:12]}",
        validation_job_id=job.validation_job_id,
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="mechanism",
        input_refs=hypothesis.source_refs,
        method="mechanism_and_assumption_presence_check",
        window=hypothesis.horizon,
        metrics={
            "mechanism_present": mechanism_present,
            "assumption_count": len(hypothesis.assumptions),
        },
        result="supported" if mechanism_present else "not_testable",
        supports_hypothesis=mechanism_present,
        disconfirms_hypothesis=False,
        confidence="low",
        limitations=[
            "Mechanism presence is a conceptual check, not empirical validation.",
        ],
        created_at_utc=now_utc(),
    )


def event_reaction_result(
    *,
    job: ValidationJob,
    hypothesis: HypothesisRecord,
    snapshot: HypothesisSnapshot,
) -> ValidationCheckResult:
    market_refs = snapshot.lineage.market_snapshot_refs
    indicator_refs = snapshot.lineage.indicator_snapshot_refs
    has_inputs = bool(market_refs or indicator_refs)

    # H3: when a cached price series exists for the symbol, compute a real
    # realized-move metric that can WEAKEN the hypothesis (the predicted
    # reaction did not show up). Degrades to the input-availability check when
    # no cache is present yet. It never returns "supported": a move does not
    # prove the mechanism.
    closes = load_cached_close_series(hypothesis.symbol)
    if closes is not None:
        assessment = assess_realized_move(closes)
        return ValidationCheckResult(
            check_id=f"valchk_{uuid4().hex[:12]}",
            validation_job_id=job.validation_job_id,
            hypothesis_id=hypothesis.hypothesis_id,
            check_type="event_reaction",
            input_refs=[*market_refs, *indicator_refs],
            method="realized_move_over_window",
            window=hypothesis.horizon,
            metrics={
                **assessment["metrics"],
                "expected_observation_count": len(hypothesis.expected_observations),
            },
            result=assessment["verdict"],
            supports_hypothesis=False,
            disconfirms_hypothesis=bool(assessment.get("weakens")),
            confidence="medium" if assessment["testable"] else "low",
            limitations=[
                "Realized move is direction-agnostic evidence; a move is not "
                "attributed to the hypothesis mechanism, so the strongest verdict "
                "here is inconclusive, never supported.",
            ],
            created_at_utc=now_utc(),
        )

    return ValidationCheckResult(
        check_id=f"valchk_{uuid4().hex[:12]}",
        validation_job_id=job.validation_job_id,
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="event_reaction",
        input_refs=[*market_refs, *indicator_refs],
        method="event_reaction_input_availability_check",
        window=hypothesis.horizon,
        metrics={
            "market_snapshot_ref_count": len(market_refs),
            "indicator_snapshot_ref_count": len(indicator_refs),
            "expected_observation_count": len(hypothesis.expected_observations),
        },
        result="inconclusive" if has_inputs else "not_testable",
        supports_hypothesis=False,
        disconfirms_hypothesis=False,
        confidence="low",
        limitations=[
            "No cached price series for the symbol yet; recording input "
            "availability only. Computes realized move once task "
            "workflow:daily-evidence has cached history.",
        ],
        created_at_utc=now_utc(),
    )


def benchmark_context_result(
    *,
    job: ValidationJob,
    hypothesis: HypothesisRecord,
    snapshot: HypothesisSnapshot,
) -> ValidationCheckResult:
    universe = {symbol.upper() for symbol in snapshot.universe}
    has_benchmark_context = "SPY" in universe and "QQQ" in universe
    return ValidationCheckResult(
        check_id=f"valchk_{uuid4().hex[:12]}",
        validation_job_id=job.validation_job_id,
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="benchmark_context",
        input_refs=[
            *snapshot.lineage.market_snapshot_refs,
            *snapshot.lineage.indicator_snapshot_refs,
        ],
        method="benchmark_universe_context_check",
        window=hypothesis.horizon,
        metrics={
            "has_spy_context": "SPY" in universe,
            "has_qqq_context": "QQQ" in universe,
            "universe": sorted(universe),
        },
        result="supported" if has_benchmark_context else "not_testable",
        supports_hypothesis=False,
        disconfirms_hypothesis=False,
        confidence="medium" if has_benchmark_context else "low",
        limitations=[
            "Benchmark presence does not estimate beta, factor exposure, or abnormal return.",
        ],
        created_at_utc=now_utc(),
    )


def disconfirmation_results(
    *,
    job: ValidationJob,
    hypothesis: HypothesisRecord,
) -> list[ValidationCheckResult]:
    results: list[ValidationCheckResult] = []
    for item in hypothesis.disconfirming_observations:
        results.append(
            ValidationCheckResult(
                check_id=f"valchk_{uuid4().hex[:12]}",
                validation_job_id=job.validation_job_id,
                hypothesis_id=hypothesis.hypothesis_id,
                check_type="disconfirmation",
                input_refs=hypothesis.source_refs,
                method="disconfirmation_item_mapping",
                window=hypothesis.horizon,
                metrics={
                    "disconfirming_observation": item,
                    "mapped": True,
                },
                result="inconclusive",
                supports_hypothesis=False,
                disconfirms_hypothesis=False,
                confidence="low",
                limitations=[
                    "MVP maps the disconfirmation item; later layers must test it with data.",
                ],
                created_at_utc=now_utc(),
            )
        )
    return results


def limitations_result(
    *,
    job: ValidationJob,
    hypothesis: HypothesisRecord,
    draft_provider: ValidationDraftProvider,
) -> ValidationCheckResult:
    draft = draft_provider.assess(hypothesis)
    limitations = [
        "Layer 6 MVP does not run return, factor, cost, or liquidity calculations.",
        "Validation result remains evidence packaging until layer-specific metrics are computed.",
    ]
    if draft:
        limitations.append(
            f"LLM interface {draft_provider.provider_name} reserved; no external assessment used."
        )
    return ValidationCheckResult(
        check_id=f"valchk_{uuid4().hex[:12]}",
        validation_job_id=job.validation_job_id,
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="limitations",
        input_refs=hypothesis.source_refs,
        method="mvp_limitation_report",
        window=hypothesis.horizon,
        metrics={
            "llm_provider": draft_provider.provider_name,
            "llm_enabled": bool(draft),
        },
        result="inconclusive",
        supports_hypothesis=False,
        disconfirms_hypothesis=False,
        confidence="low",
        limitations=limitations,
        created_at_utc=now_utc(),
    )


def build_validation_results(
    *,
    snapshot: HypothesisSnapshot,
    jobs: list[ValidationJob],
    draft_provider: ValidationDraftProvider | None = None,
    backtest_provider: BacktestEvidenceProvider | None = None,
) -> list[ValidationCheckResult]:
    provider = draft_provider or NullValidationDraftProvider()
    backtest = backtest_provider or NullBacktestEvidenceProvider()
    by_id = {record.hypothesis_id: record for record in snapshot.records}
    results: list[ValidationCheckResult] = []
    for job in jobs:
        hypothesis = by_id[job.hypothesis_id]
        results.extend(
            [
                source_validity_result(job=job, hypothesis=hypothesis),
                mechanism_result(job=job, hypothesis=hypothesis),
                event_reaction_result(job=job, hypothesis=hypothesis, snapshot=snapshot),
                benchmark_context_result(job=job, hypothesis=hypothesis, snapshot=snapshot),
                *disconfirmation_results(job=job, hypothesis=hypothesis),
                backtest_evidence_result(
                    job=job,
                    hypothesis=hypothesis,
                    snapshot=snapshot,
                    provider=backtest,
                ),
                limitations_result(
                    job=job,
                    hypothesis=hypothesis,
                    draft_provider=provider,
                ),
            ]
        )
    return results


def build_validation_quality(
    *,
    snapshot: HypothesisSnapshot,
    jobs: list[ValidationJob],
    results: list[ValidationCheckResult],
) -> ValidationQuality:
    missing_required_fields: dict[str, list[str]] = {}
    blocked_language_hits: dict[str, list[str]] = {}

    for result in results:
        missing: list[str] = []
        if not result.input_refs and result.check_type not in {
            "benchmark_context",
            "backtest",
            "event_reaction",
        }:
            missing.append("input_refs")
        if not result.method:
            missing.append("method")
        if not result.window:
            missing.append("window")
        if not result.limitations:
            missing.append("limitations")
        if result.result not in {
            "supported",
            "weakened",
            "disconfirmed",
            "inconclusive",
            "not_testable",
        }:
            missing.append("result")
        if missing:
            missing_required_fields[result.check_id] = missing
        hits = find_blocked_language(result_text_for_guard(result))
        if hits:
            blocked_language_hits[result.check_id] = hits

    hypothesis_source_linked = all(
        record.source_interpretation_ids and record.source_event_ids and record.source_refs
        for record in snapshot.records
    )
    validation_jobs_created = bool(jobs) and len(jobs) == len(snapshot.records)
    source_validity_checked = all(
        any(
            result.hypothesis_id == job.hypothesis_id
            and result.check_type == "source_validity"
            for result in results
        )
        for job in jobs
    )
    at_least_one_market_check = any(
        result.check_type == "event_reaction" for result in results
    )
    at_least_one_disconfirmation_check = all(
        any(
            result.hypothesis_id == job.hypothesis_id
            and result.check_type == "disconfirmation"
            for result in results
        )
        for job in jobs
    )
    benchmark_context_present = any(
        result.check_type == "benchmark_context" and result.result == "supported"
        for result in results
    )
    no_blocked_language = not blocked_language_hits
    limitations_present = all(result.limitations for result in results)
    result_not_overclaimed = all(
        result.result
        in {"supported", "weakened", "disconfirmed", "inconclusive", "not_testable"}
        for result in results
    )
    lineage_complete = bool(
        snapshot.hypothesis_snapshot_id and snapshot.receipt_ref and snapshot.lineage
    )
    notes: list[str] = []
    if not jobs:
        notes.append("no validation jobs were created")
    if not benchmark_context_present:
        notes.append("SPY and QQQ benchmark context is missing from hypothesis universe")

    ok = (
        bool(results)
        and hypothesis_source_linked
        and validation_jobs_created
        and source_validity_checked
        and at_least_one_market_check
        and at_least_one_disconfirmation_check
        and benchmark_context_present
        and no_blocked_language
        and limitations_present
        and result_not_overclaimed
        and lineage_complete
        and not missing_required_fields
    )
    return ValidationQuality(
        ok=ok,
        job_count=len(jobs),
        result_count=len(results),
        hypothesis_source_linked=hypothesis_source_linked,
        validation_jobs_created=validation_jobs_created,
        source_validity_checked=source_validity_checked,
        at_least_one_market_check=at_least_one_market_check,
        at_least_one_disconfirmation_check=at_least_one_disconfirmation_check,
        benchmark_context_present=benchmark_context_present,
        no_proposal_or_execution_language=no_blocked_language,
        limitations_present=limitations_present,
        result_not_overclaimed=result_not_overclaimed,
        lineage_complete=lineage_complete,
        missing_required_fields=missing_required_fields,
        blocked_language_hits=blocked_language_hits,
        notes=notes,
    )


def proposal_handoff(results: list[ValidationCheckResult]) -> list[str]:
    grouped: dict[str, list[str]] = {}
    for result in results:
        grouped.setdefault(result.hypothesis_id, []).append(result.result)
    handoff = []
    for hypothesis_id, result_values in grouped.items():
        handoff.append(
            f"{hypothesis_id}: validation evidence includes "
            f"{', '.join(sorted(set(result_values)))}; human review required before proposal."
        )
    return handoff


def snapshot_review_questions(results: list[ValidationCheckResult]) -> list[str]:
    questions = [
        "Which validation result is most dependent on missing market data?",
        "Which disconfirmation item should be tested with real metrics first?",
        "Did any validation language drift toward proposal or execution?",
        "Which hypothesis should be rejected before proposal to reduce bias?",
    ]
    if any(result.result == "not_testable" for result in results):
        questions.append("Which not-testable result needs better data or a narrower hypothesis?")
    return questions


def persist_validation_bundle(
    *,
    source: ValidationSourceSpec,
    input_hypothesis_snapshot: HypothesisSnapshot,
    jobs: list[ValidationJob],
    results: list[ValidationCheckResult],
) -> ValidationBundle:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    snapshot_id = f"vals_{stamp}_{suffix}"
    receipt_id = f"receipt_{snapshot_id}"
    output_ref = VALIDATION_NORMALIZED_ROOT / f"{snapshot_id}.json"
    receipt_ref = VALIDATION_RECEIPT_ROOT / f"{receipt_id}.json"
    quality = build_validation_quality(
        snapshot=input_hypothesis_snapshot,
        jobs=jobs,
        results=results,
    )
    output_payload = {
        "validation_snapshot_id": snapshot_id,
        "input_hypothesis_snapshot_id": input_hypothesis_snapshot.hypothesis_snapshot_id,
        "universe": input_hypothesis_snapshot.universe,
        "jobs": [job.model_dump(mode="json") for job in jobs],
        "results": [result.model_dump(mode="json") for result in results],
    }
    output_hash = sha256_text(
        json.dumps(output_payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    lineage = ValidationLineage(
        source=source,
        input_hypothesis_snapshot_id=input_hypothesis_snapshot.hypothesis_snapshot_id,
        input_hypothesis_receipt_ref=input_hypothesis_snapshot.receipt_ref,
        hypothesis_ids=[record.hypothesis_id for record in input_hypothesis_snapshot.records],
        interpretation_snapshot_id=(
            input_hypothesis_snapshot.input_interpretation_snapshot_id
        ),
        event_snapshot_id=input_hypothesis_snapshot.lineage.input_event_snapshot_id,
        market_snapshot_refs=input_hypothesis_snapshot.lineage.market_snapshot_refs,
        indicator_snapshot_refs=input_hypothesis_snapshot.lineage.indicator_snapshot_refs,
        method=source.method,
        model_provider=source.llm_provider if source.llm_enabled else None,
        prompt_template_version=source.template_version,
        computed_at_utc=now_utc(),
        output_hash=output_hash,
        output_ref=display_path(output_ref),
    )
    snapshot = ValidationSnapshot(
        validation_snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        input_hypothesis_snapshot_id=input_hypothesis_snapshot.hypothesis_snapshot_id,
        universe=input_hypothesis_snapshot.universe,
        job_count=len(jobs),
        result_count=len(results),
        jobs=jobs,
        results=results,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(output_ref),
        receipt_ref=display_path(receipt_ref),
        execution_allowed=False,
        proposal_handoff=proposal_handoff(results),
        review_questions=snapshot_review_questions(results),
    )
    receipt = ValidationReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source_input": "ValidationSourceSpec + HypothesisSnapshot",
            "jobs": "ValidationJob per HypothesisRecord",
            "source_validity": "source refs and upstream ids checked",
            "mechanism": "mechanism and assumptions checked",
            "event_reaction": "event-reaction input availability checked",
            "benchmark_context": "SPY/QQQ benchmark context checked",
            "disconfirmation": "hypothesis disconfirmation items mapped",
            "backtest": "vectorbt research backtest evidence recorded without authority",
            "limitations": "known validation limitations recorded",
            "quality": "no overclaim, no execution/proposal language, lineage gates",
            "snapshot": "ValidationSnapshot",
            "receipt": "ValidationReceipt",
            "consumer_handoff": "proposal/human review only",
        },
        snapshot=snapshot,
        status="ok" if quality.ok else "warning",
    )
    write_json(output_ref, output_payload)
    write_json(receipt_ref, receipt.model_dump(mode="json"))
    return ValidationBundle(
        source=source,
        input_hypothesis_snapshot=input_hypothesis_snapshot,
        jobs=jobs,
        results=results,
        quality=quality,
        lineage=lineage,
        snapshot=snapshot,
        receipt=receipt,
    )


def build_validation_bundle_from_hypothesis_snapshot(
    hypothesis_snapshot: HypothesisSnapshot | dict[str, Any],
    *,
    llm_enabled: bool = False,
    hermes_root: str | Path = "/root/projects/hermes-agent",
    backtest_provider: BacktestEvidenceProvider | None = None,
) -> ValidationBundle:
    snapshot = (
        hypothesis_snapshot
        if isinstance(hypothesis_snapshot, HypothesisSnapshot)
        else HypothesisSnapshot.model_validate(hypothesis_snapshot)
    )
    source = ValidationSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesValidationDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=str(hermes_root),
        config={
            "input_hypothesis_snapshot_id": snapshot.hypothesis_snapshot_id,
            "record_count": snapshot.record_count,
        },
    )
    provider: ValidationDraftProvider
    if llm_enabled:
        provider = HermesValidationDraftProvider(hermes_root=hermes_root)
    else:
        provider = NullValidationDraftProvider()
    jobs = create_validation_jobs(snapshot)
    results = build_validation_results(
        snapshot=snapshot,
        jobs=jobs,
        draft_provider=provider,
        backtest_provider=backtest_provider,
    )
    return persist_validation_bundle(
        source=source,
        input_hypothesis_snapshot=snapshot,
        jobs=jobs,
        results=results,
    )
