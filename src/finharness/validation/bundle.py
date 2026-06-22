"""Validation bundle persistence and quality gates."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.hypotheses import HypothesisSnapshot
from finharness.market_data import display_path, sha256_text
from finharness.validation._util import (
    find_blocked_language,
    now_utc,
    result_text_for_guard,
    write_json,
)
from finharness.validation.backtest import backtest_result_respects_rung
from finharness.validation.checks import build_validation_results, create_validation_jobs
from finharness.validation.models import (
    BacktestEvidenceProvider,
    ValidationBundle,
    ValidationCheckResult,
    ValidationDraftProvider,
    ValidationJob,
    ValidationLineage,
    ValidationQuality,
    ValidationReceipt,
    ValidationSnapshot,
    ValidationSourceSpec,
)
from finharness.validation.providers import (
    HermesValidationDraftProvider,
    NullValidationDraftProvider,
)


def validation_storage_roots() -> tuple[Path, Path]:
    from finharness import validation as validation_package

    return (
        validation_package.VALIDATION_NORMALIZED_ROOT,
        validation_package.VALIDATION_RECEIPT_ROOT,
    )


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
            "linked",
            "present",
            "well_formed",
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
        result.check_type == "benchmark_context" and result.result == "present"
        for result in results
    )
    no_blocked_language = not blocked_language_hits
    limitations_present = all(result.limitations for result in results)
    result_not_overclaimed = all(
        result.result
        in {
            "supported",
            "linked",
            "present",
            "well_formed",
            "weakened",
            "disconfirmed",
            "inconclusive",
            "not_testable",
        }
        and backtest_result_respects_rung(result)
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
    normalized_root, receipt_root = validation_storage_roots()
    output_ref = normalized_root / f"{snapshot_id}.json"
    receipt_ref = receipt_root / f"{receipt_id}.json"
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
