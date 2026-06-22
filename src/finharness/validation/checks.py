"""Validation check construction."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from finharness.hypotheses import HypothesisRecord, HypothesisSnapshot
from finharness.validation._util import now_utc
from finharness.validation.backtest import backtest_evidence_result
from finharness.validation.models import (
    BacktestEvidenceProvider,
    ValidationCheckResult,
    ValidationDraftProvider,
    ValidationJob,
)
from finharness.validation.providers import (
    NullBacktestEvidenceProvider,
    NullValidationDraftProvider,
)


def _load_cached_close_series(symbol: str) -> list[float] | None:
    from finharness import validation as validation_package

    return validation_package.load_cached_close_series(symbol)


def _assess_realized_move(closes: list[float]) -> dict[str, Any]:
    from finharness import validation as validation_package

    return validation_package.assess_realized_move(closes)


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
        result="linked" if linked else "not_testable",
        supports_hypothesis=False,
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
        result="present" if mechanism_present else "not_testable",
        supports_hypothesis=False,
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
    closes = _load_cached_close_series(hypothesis.symbol)
    if closes is not None:
        assessment = _assess_realized_move(closes)
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
        result="present" if has_benchmark_context else "not_testable",
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
