"""Proposal persistence and top-level bundle builder."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.market_data import display_path, sha256_text
from finharness.proposal._util import now_utc, write_json
from finharness.proposal.formulation import build_proposal_candidates
from finharness.proposal.models import (
    ProposalBundle,
    ProposalCandidate,
    ProposalLineage,
    ProposalReceipt,
    ProposalSnapshot,
    ProposalSourceSpec,
)
from finharness.proposal.providers import (
    HermesProposalDraftProvider,
    NullProposalDraftProvider,
    ProposalDraftProvider,
)
from finharness.proposal.quality import (
    build_proposal_quality,
    risk_gate_handoff,
    snapshot_review_questions,
)
from finharness.validation import ValidationSnapshot


def proposal_storage_roots() -> tuple[Path, Path]:
    from finharness import proposal as proposal_package

    return (
        proposal_package.PROPOSAL_NORMALIZED_ROOT,
        proposal_package.PROPOSAL_RECEIPT_ROOT,
    )


def persist_proposal_bundle(
    *,
    source: ProposalSourceSpec,
    input_validation_snapshot: ValidationSnapshot,
    candidates: list[ProposalCandidate],
) -> ProposalBundle:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    snapshot_id = f"props_{stamp}_{suffix}"
    receipt_id = f"receipt_{snapshot_id}"
    normalized_root, receipt_root = proposal_storage_roots()
    output_ref = normalized_root / f"{snapshot_id}.json"
    receipt_ref = receipt_root / f"{receipt_id}.json"
    quality = build_proposal_quality(
        validation_snapshot=input_validation_snapshot,
        candidates=candidates,
    )
    output_payload = {
        "proposal_snapshot_id": snapshot_id,
        "input_validation_snapshot_id": input_validation_snapshot.validation_snapshot_id,
        "universe": input_validation_snapshot.universe,
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }
    output_hash = sha256_text(
        json.dumps(output_payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    lineage = ProposalLineage(
        source=source,
        input_validation_snapshot_id=input_validation_snapshot.validation_snapshot_id,
        input_validation_receipt_ref=input_validation_snapshot.receipt_ref,
        validation_result_ids=[
            result.check_id for result in input_validation_snapshot.results
        ],
        hypothesis_ids=input_validation_snapshot.lineage.hypothesis_ids,
        validation_transform_version=input_validation_snapshot.lineage.transform_version,
        method=source.method,
        model_provider=source.llm_provider if source.llm_enabled else None,
        prompt_template_version=source.template_version,
        computed_at_utc=now_utc(),
        output_hash=output_hash,
        output_ref=display_path(output_ref),
    )
    snapshot = ProposalSnapshot(
        proposal_snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        input_validation_snapshot_id=input_validation_snapshot.validation_snapshot_id,
        universe=input_validation_snapshot.universe,
        candidate_count=len(candidates),
        candidates=candidates,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(output_ref),
        receipt_ref=display_path(receipt_ref),
        execution_allowed=False,
        risk_gate_handoff=risk_gate_handoff(candidates),
        review_questions=snapshot_review_questions(candidates),
    )
    receipt = ProposalReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source_input": "ProposalSourceSpec + ValidationSnapshot",
            "candidate_selection": "ValidationResult groups by hypothesis",
            "proposal_formulation": "structured action candidate for risk review only",
            "invalidation": "candidate invalidation triggers required",
            "constraints": "risk gate checks and constraints required",
            "quality": "no execution authority, no orders, no final sizing",
            "lineage": "ValidationSnapshot refs, result ids, output hash/ref",
            "snapshot": "ProposalSnapshot",
            "receipt": "ProposalReceipt",
            "consumer_handoff": "risk gate review only",
        },
        snapshot=snapshot,
        status="ok" if quality.ok else "warning",
    )
    write_json(output_ref, output_payload)
    write_json(receipt_ref, receipt.model_dump(mode="json"))
    return ProposalBundle(
        source=source,
        input_validation_snapshot=input_validation_snapshot,
        candidates=candidates,
        quality=quality,
        lineage=lineage,
        snapshot=snapshot,
        receipt=receipt,
    )


def build_proposal_bundle_from_validation_snapshot(
    validation_snapshot: ValidationSnapshot | dict[str, Any],
    *,
    llm_enabled: bool = False,
    hermes_root: str | Path = "/root/projects/hermes-agent",
) -> ProposalBundle:
    snapshot = (
        validation_snapshot
        if isinstance(validation_snapshot, ValidationSnapshot)
        else ValidationSnapshot.model_validate(validation_snapshot)
    )
    source = ProposalSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesProposalDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=str(hermes_root),
        config={
            "input_validation_snapshot_id": snapshot.validation_snapshot_id,
            "result_count": snapshot.result_count,
        },
    )
    provider: ProposalDraftProvider
    if llm_enabled:
        provider = HermesProposalDraftProvider(hermes_root=hermes_root)
    else:
        provider = NullProposalDraftProvider()
    candidates = build_proposal_candidates(
        validation_snapshot=snapshot,
        draft_provider=provider,
    )
    return persist_proposal_bundle(
        source=source,
        input_validation_snapshot=snapshot,
        candidates=candidates,
    )
