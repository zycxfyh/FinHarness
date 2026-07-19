"""Commit-boundary valuation agreement for production capital imports."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

from finharness.artifact_store import ArtifactStore
from finharness.capital_import_contract import ImportFinding, completeness_status
from finharness.position_valuation import (
    BASE_VALUATION_POLICY_V1,
    ValuationAssessment,
    assess_position_valuation,
    evidence_from_position,
)
from finharness.statecore.import_models import ImportBatch, ReceiptManifest
from finharness.statecore.models import Position, Snapshot
from finharness.statecore.store import StateCoreRecord, StateCoreStoreError

PRODUCTION_VALUATION_SOURCES = frozenset(
    {
        "personal_finance_export",
        "beancount_ledger",
        "broker_read",
    }
)

_VALUATION_CODE_MARKERS = (
    "valuation_",
    "market_value_",
    "unit_price_",
    "price_currency_",
    "price_source_",
    "valued_at_",
    "fx_",
    "market_price_",
)


def _is_valuation_finding(finding: Any) -> bool:
    code = (
        finding.get("code", "")
        if isinstance(finding, dict)
        else getattr(finding, "code", "") or ""
    )
    if not code:
        return False
    if "valuation" in code or code.endswith("_stale"):
        return True
    return any(code.startswith(prefix) for prefix in _VALUATION_CODE_MARKERS)


def _as_finding_dict(finding: Any) -> dict[str, Any]:
    if isinstance(finding, ImportFinding):
        return finding.as_dict()
    if isinstance(finding, dict):
        return dict(finding)
    return {
        "code": getattr(finding, "code", ""),
        "severity": getattr(finding, "severity", ""),
        "message": getattr(finding, "message", ""),
        "record_type": getattr(finding, "record_type", None),
        "record_number": getattr(finding, "record_number", None),
        "field": getattr(finding, "field", None),
        "record_id": getattr(finding, "record_id", None),
    }


def _normalize_tuple(finding: Any) -> tuple:
    data = _as_finding_dict(finding)
    return (
        data.get("code") or "",
        data.get("severity") or "",
        data.get("record_type"),
        data.get("record_number"),
        data.get("field"),
        data.get("record_id"),
    )


def assess_positions(
    positions: Sequence[Position],
    *,
    evaluated_at_utc: str,
    record_numbers: dict[str, int] | None = None,
    allow_unknown_legacy: bool = False,
) -> list[ValuationAssessment]:
    numbers = record_numbers or {}
    return [
        assess_position_valuation(
            evidence_from_position(position),
            record_id=position.position_id,
            record_number=numbers.get(position.position_id),
            evaluated_at_utc=evaluated_at_utc,
            policy=BASE_VALUATION_POLICY_V1,
            check_freshness=True,
            allow_unknown_legacy=allow_unknown_legacy,
        )
        for position in positions
    ]


def apply_assessments_to_positions(
    positions: Sequence[Position],
    assessments: Sequence[ValuationAssessment],
) -> list[Position]:
    """Mutate positions in-place with derived valuation status.

    Returns the same list references so SQLAlchemy session merge finds them.
    """
    updated: list[Position] = []
    for position, assessment in zip(positions, assessments, strict=True):
        position.valuation_status = assessment.status.value
        updated.append(position)
    return updated


def merge_valuation_findings(
    base_findings: Iterable[Any],
    assessments: Sequence[ValuationAssessment],
) -> list[ImportFinding]:
    kept: list[ImportFinding] = []
    for finding in base_findings:
        data = _as_finding_dict(finding)
        if _is_valuation_finding(data):
            continue
        kept.append(
            ImportFinding(
                code=str(data.get("code") or ""),
                severity=data.get("severity") or "partial",  # type: ignore[arg-type]
                message=str(data.get("message") or ""),
                record_type=data.get("record_type"),
                record_number=data.get("record_number"),
                field=data.get("field"),
                record_id=data.get("record_id"),
            )
        )
    valuation: list[ImportFinding] = []
    for assessment in assessments:
        valuation.extend(assessment.findings)
    return [*kept, *valuation]


def observed_at_from_batch(batch: ImportBatch) -> str:
    clocks = batch.time_semantics or {}
    observed = clocks.get("observed_at_utc")
    if not observed:
        raise StateCoreStoreError("valuation_policy_mismatch: batch missing observed_at_utc")
    return str(observed)


def validate_import_valuation_contract(
    *,
    source: str,
    batch: ImportBatch,
    manifest: ReceiptManifest,
    records: Sequence[StateCoreRecord],
    artifact_store: ArtifactStore,
) -> None:
    """Fail closed before any DB write if valuation surfaces disagree."""
    if source not in PRODUCTION_VALUATION_SOURCES:
        return
    snapshots = [record for record in records if isinstance(record, Snapshot)]
    positions = [record for record in records if isinstance(record, Position)]
    target = [snap for snap in snapshots if snap.snapshot_id == manifest.snapshot_id]
    if len(target) != 1:
        raise StateCoreStoreError(
            f"valuation_snapshot_mismatch: expected one snapshot for "
            f"{manifest.snapshot_id}, got {len(target)}"
        )
    snapshot = target[0]
    observed = observed_at_from_batch(batch)
    assessments = assess_positions(positions, evaluated_at_utc=observed)
    derived_by_id = {
        position.position_id: assessment
        for position, assessment in zip(positions, assessments, strict=True)
    }
    for position in positions:
        assessment = derived_by_id[position.position_id]
        if position.valuation_status != assessment.status.value:
            raise StateCoreStoreError(
                "valuation_status_mismatch: "
                f"{position.position_id} stored={position.valuation_status} "
                f"derived={assessment.status.value}"
            )
        if assessment.policy_id != BASE_VALUATION_POLICY_V1.policy_id:
            raise StateCoreStoreError("valuation_policy_mismatch")

    expected_valuation = []
    for assessment in assessments:
        expected_valuation.extend(_normalize_tuple(f) for f in assessment.findings)
    expected_counter = Counter(expected_valuation)

    batch_valuation = [
        _normalize_tuple(f) for f in (batch.findings or []) if _is_valuation_finding(f)
    ]
    snap_findings = list((snapshot.payload or {}).get("findings") or [])
    snap_valuation = [_normalize_tuple(f) for f in snap_findings if _is_valuation_finding(f)]

    try:
        receipt_bytes = artifact_store.read(manifest.receipt_artifact_id)
        receipt_payload = json.loads(receipt_bytes)
    except Exception as exc:
        raise StateCoreStoreError(
            f"valuation_receipt_mismatch: cannot read receipt artifact: {exc}"
        ) from exc
    receipt_findings = list(receipt_payload.get("findings") or [])
    receipt_valuation = [
        _normalize_tuple(f) for f in receipt_findings if _is_valuation_finding(f)
    ]

    if Counter(batch_valuation) != expected_counter:
        raise StateCoreStoreError(
            "valuation_findings_mismatch: batch findings diverge from "
            f"canonical assessment batch={batch_valuation} expected={expected_valuation}"
        )
    if Counter(snap_valuation) != expected_counter:
        raise StateCoreStoreError(
            "valuation_snapshot_mismatch: snapshot findings diverge from "
            f"canonical assessment snap={snap_valuation} expected={expected_valuation}"
        )
    if Counter(receipt_valuation) != expected_counter:
        raise StateCoreStoreError(
            "valuation_receipt_mismatch: receipt findings diverge from "
            f"canonical assessment receipt={receipt_valuation} expected={expected_valuation}"
        )

    expected_completeness = completeness_status(
        [
            ImportFinding(
                code=str(_as_finding_dict(f).get("code") or ""),
                severity=_as_finding_dict(f).get("severity") or "partial",  # type: ignore[arg-type]
                message=str(_as_finding_dict(f).get("message") or ""),
                record_type=_as_finding_dict(f).get("record_type"),
                record_number=_as_finding_dict(f).get("record_number"),
                field=_as_finding_dict(f).get("field"),
                record_id=_as_finding_dict(f).get("record_id"),
            )
            for f in (batch.findings or [])
        ]
    )
    snap_completeness = (snapshot.payload or {}).get("completeness_status")
    receipt_completeness = receipt_payload.get("completeness_status")
    if (
        batch.completeness_status != expected_completeness
        or snap_completeness != batch.completeness_status
        or receipt_completeness != batch.completeness_status
    ):
        raise StateCoreStoreError(
            "valuation_completeness_mismatch: "
            f"batch={batch.completeness_status} snapshot={snap_completeness} "
            f"receipt={receipt_completeness} expected={expected_completeness}"
        )
