"""Hypothesis persistence and top-level bundle builder."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.hypotheses._util import now_utc, write_json
from finharness.hypotheses.formulation import (
    formulate_hypothesis_record,
    select_hypothesis_candidates,
)
from finharness.hypotheses.models import (
    HypothesisBundle,
    HypothesisLineage,
    HypothesisReceipt,
    HypothesisRecord,
    HypothesisSnapshot,
    HypothesisSourceSpec,
)
from finharness.hypotheses.providers import (
    HermesHypothesisDraftProvider,
    HypothesisDraftProvider,
    NullHypothesisDraftProvider,
)
from finharness.hypotheses.quality import (
    build_hypothesis_quality,
    snapshot_review_questions,
    validation_handoff,
)
from finharness.interpretation import InterpretationSnapshot
from finharness.market_data import display_path, sha256_text


def hypothesis_storage_roots() -> tuple[Path, Path]:
    from finharness import hypotheses as hypotheses_package

    return (
        hypotheses_package.HYPOTHESIS_NORMALIZED_ROOT,
        hypotheses_package.HYPOTHESIS_RECEIPT_ROOT,
    )


def persist_hypothesis_bundle(
    *,
    source: HypothesisSourceSpec,
    input_interpretation_snapshot: InterpretationSnapshot,
    records: list[HypothesisRecord],
) -> HypothesisBundle:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    snapshot_id = f"hyps_{stamp}_{suffix}"
    receipt_id = f"receipt_{snapshot_id}"
    normalized_root, receipt_root = hypothesis_storage_roots()
    output_ref = normalized_root / f"{snapshot_id}.json"
    receipt_ref = receipt_root / f"{receipt_id}.json"
    quality = build_hypothesis_quality(records)
    output_payload = {
        "hypothesis_snapshot_id": snapshot_id,
        "input_interpretation_snapshot_id": (
            input_interpretation_snapshot.interpretation_snapshot_id
        ),
        "universe": input_interpretation_snapshot.universe,
        "records": [record.model_dump(mode="json") for record in records],
    }
    output_hash = sha256_text(
        json.dumps(output_payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    lineage = HypothesisLineage(
        source=source,
        input_interpretation_snapshot_id=(
            input_interpretation_snapshot.interpretation_snapshot_id
        ),
        input_interpretation_receipt_ref=input_interpretation_snapshot.receipt_ref,
        input_event_snapshot_id=input_interpretation_snapshot.input_event_snapshot_id,
        interpretation_record_ids=[
            interpretation_id
            for record in records
            for interpretation_id in record.source_interpretation_ids
        ],
        event_record_ids=[event_id for record in records for event_id in record.source_event_ids],
        market_snapshot_refs=input_interpretation_snapshot.lineage.market_snapshot_refs,
        indicator_snapshot_refs=input_interpretation_snapshot.lineage.indicator_snapshot_refs,
        method=source.method,
        model_provider=source.llm_provider if source.llm_enabled else None,
        prompt_template_version=source.template_version,
        computed_at_utc=now_utc(),
        output_hash=output_hash,
        output_ref=display_path(output_ref),
    )
    snapshot = HypothesisSnapshot(
        hypothesis_snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        input_interpretation_snapshot_id=(
            input_interpretation_snapshot.interpretation_snapshot_id
        ),
        universe=input_interpretation_snapshot.universe,
        record_count=len(records),
        records=records,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(output_ref),
        receipt_ref=display_path(receipt_ref),
        execution_allowed=False,
        validation_handoff=validation_handoff(records),
        review_questions=snapshot_review_questions(records),
    )
    receipt = HypothesisReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source_input": "HypothesisSourceSpec + InterpretationSnapshot",
            "candidate_selection": "source-backed InterpretationRecord selection",
            "formulate": "rule-guided falsifiable hypothesis template",
            "disconfirming_evidence": "explicit failure observations required",
            "validation_plan": "next-layer validation checks only",
            "quality": "source, testability, disconfirmation, no-recommendation gates",
            "lineage": "InterpretationSnapshot refs, ids, output hash/ref",
            "snapshot": "HypothesisSnapshot",
            "receipt": "HypothesisReceipt",
            "consumer_handoff": "validation/review inputs only",
            "review_hook": "human review before validation promotion",
        },
        snapshot=snapshot,
        status="ok" if quality.ok else "warning",
    )
    write_json(output_ref, output_payload)
    write_json(receipt_ref, receipt.model_dump(mode="json"))
    return HypothesisBundle(
        source=source,
        input_interpretation_snapshot=input_interpretation_snapshot,
        records=records,
        quality=quality,
        lineage=lineage,
        snapshot=snapshot,
        receipt=receipt,
    )


def build_hypothesis_bundle_from_interpretation_snapshot(
    interpretation_snapshot: InterpretationSnapshot | dict[str, Any],
    *,
    max_hypotheses: int = 10,
    symbols: list[str] | None = None,
    llm_enabled: bool = False,
    hermes_root: str | Path = "/root/projects/hermes-agent",
) -> HypothesisBundle:
    snapshot = (
        interpretation_snapshot
        if isinstance(interpretation_snapshot, InterpretationSnapshot)
        else InterpretationSnapshot.model_validate(interpretation_snapshot)
    )
    source = HypothesisSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesHypothesisDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=str(hermes_root),
        config={
            "max_hypotheses": max_hypotheses,
            "symbols": symbols or [],
        },
    )
    provider: HypothesisDraftProvider
    if llm_enabled:
        provider = HermesHypothesisDraftProvider(hermes_root=hermes_root)
    else:
        provider = NullHypothesisDraftProvider()
    candidates = select_hypothesis_candidates(
        snapshot,
        max_hypotheses=max_hypotheses,
        symbols=symbols,
    )
    records = [
        formulate_hypothesis_record(record, draft_provider=provider)
        for record in candidates
    ]
    return persist_hypothesis_bundle(
        source=source,
        input_interpretation_snapshot=snapshot,
        records=records,
    )
