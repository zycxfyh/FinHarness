"""Hypothesis quality gates and handoff helpers."""

from __future__ import annotations

import re

from finharness.hypotheses._constants import VALIDATED_PATTERNS
from finharness.hypotheses._util import find_blocked_language, record_text_for_guard
from finharness.hypotheses.models import HypothesisQuality, HypothesisRecord


def missing_hypothesis_fields(record: HypothesisRecord) -> list[str]:
    missing: list[str] = []
    if not record.source_interpretation_ids:
        missing.append("source_interpretation_ids")
    if not record.source_event_ids:
        missing.append("source_event_ids")
    if not record.source_refs:
        missing.append("source_refs")
    if not record.mechanism:
        missing.append("mechanism")
    if not record.hypothesis:
        missing.append("hypothesis")
    if not record.horizon or record.horizon == "unknown":
        missing.append("horizon")
    if not record.expected_observations:
        missing.append("expected_observations")
    if not record.disconfirming_observations:
        missing.append("disconfirming_observations")
    if not record.validation_plan:
        missing.append("validation_plan")
    if not record.assumptions:
        missing.append("assumptions")
    if record.status != "ready_for_validation":
        missing.append("status")
    return missing


def build_hypothesis_quality(records: list[HypothesisRecord]) -> HypothesisQuality:
    missing_required_fields: dict[str, list[str]] = {}
    blocked_language_hits: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    duplicate_ids: list[str] = []

    for record in records:
        missing = missing_hypothesis_fields(record)
        if missing:
            missing_required_fields[record.hypothesis_id] = missing

        hits = find_blocked_language(record_text_for_guard(record))
        if hits:
            blocked_language_hits[record.hypothesis_id] = hits

        key = record.hypothesis.strip().lower()
        if key in seen:
            duplicate_ids.extend([seen[key], record.hypothesis_id])
        else:
            seen[key] = record.hypothesis_id

    source_backed = all(
        record.source_interpretation_ids and record.source_event_ids and record.source_refs
        for record in records
    )
    testable = all(bool(record.expected_observations) for record in records)
    disconfirming = all(bool(record.disconfirming_observations) for record in records)
    horizon_present = all(record.horizon and record.horizon != "unknown" for record in records)
    validation_plan_present = all(bool(record.validation_plan) for record in records)
    no_blocked_language = not blocked_language_hits
    claim_not_marked_validated = all(
        not re.search("|".join(VALIDATED_PATTERNS), record_text_for_guard(record).lower())
        for record in records
    )
    temporal_context_separated = all(
        any("event" in item.lower() or "timing" in item.lower() for item in record.assumptions)
        for record in records
    )
    duplicate_check = not duplicate_ids
    notes: list[str] = []
    if not records:
        notes.append("no interpretation records were promoted into hypotheses")

    ok = (
        bool(records)
        and source_backed
        and testable
        and disconfirming
        and horizon_present
        and validation_plan_present
        and no_blocked_language
        and claim_not_marked_validated
        and temporal_context_separated
        and duplicate_check
        and not missing_required_fields
    )
    return HypothesisQuality(
        ok=ok,
        record_count=len(records),
        source_backed_hypotheses=source_backed,
        testable_predictions_present=testable,
        disconfirming_evidence_present=disconfirming,
        horizon_present=horizon_present,
        validation_plan_present=validation_plan_present,
        no_execution_language=no_blocked_language,
        no_recommendation_language=no_blocked_language,
        claim_not_marked_validated=claim_not_marked_validated,
        temporal_context_separated=temporal_context_separated,
        duplicate_hypothesis_check=duplicate_check,
        missing_required_fields=missing_required_fields,
        blocked_language_hits=blocked_language_hits,
        duplicate_hypothesis_ids=sorted(set(duplicate_ids)),
        notes=notes,
    )


def validation_handoff(records: list[HypothesisRecord]) -> list[str]:
    return [
        f"{record.hypothesis_id}: validate {record.symbol} through "
        f"{', '.join(check.check_type for check in record.validation_plan)}"
        for record in records
    ]


def snapshot_review_questions(records: list[HypothesisRecord]) -> list[str]:
    questions = [
        "Which hypothesis has the weakest source backing?",
        "Which disconfirming observation should be tested first?",
        "Which validation plan is too vague for layer 6?",
        "Did any hypothesis drift into recommendation language?",
    ]
    if records:
        questions.append("Which hypothesis should be rejected before validation to reduce bias?")
    return questions
