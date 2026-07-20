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


def valuation_assessment_summary(
    positions: Sequence[Position],
    *,
    evaluated_at_utc: str,
) -> dict[str, object]:
    """Build an immutable summary for snapshot payload and receipt.

    All three adapters must use this helper instead of hardcoding policy_id.
    """
    status_counts: dict[str, int] = {}
    for position in positions:
        status = position.valuation_status or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "policy_id": BASE_VALUATION_POLICY_V1.policy_id,
        "evaluated_at_utc": evaluated_at_utc,
        "status_counts": status_counts,
    }


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
                severity=data.get("severity") or "partial",
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
        raise _import_error("valuation_policy_mismatch: batch missing observed_at_utc")
    return str(observed)


class ValuationContractError(ValueError):
    """Raised when a production import violates the valuation surface agreement."""


def _import_error(message: str) -> Exception:
    return ValuationContractError(message)


# Mapping from batch.record_counts keys to Python class names.
_RECORD_COUNT_KEY_TO_CLASS: dict[str, str] = {
    "position": "Position",
    "account": "Account",
    "snapshot": "Snapshot",
    "cashflow": "CashflowEvent",
    "liability": "Liability",
    "tax_event": "TaxEvent",
    "insurance": "InsurancePolicy",
    "goal": "FinancialGoal",
    "document": "DocumentRef",
}

# Source-domain keys whose counts must always be verified against actual records.
# Infrastructure keys (Account, Snapshot) are only verified when present in
# batch_counts because their count semantics vary across adapters.
_DIRECT_SOURCE_DOMAIN_KEYS: frozenset[str] = frozenset({
    "position", "cashflow", "liability", "tax_event",
    "insurance", "goal", "document",
})


def validate_import_valuation_contract(  # noqa: C901 -- ordered surface agreement checks
    *,
    source: str,
    batch: ImportBatch,
    manifest: ReceiptManifest,
    records: Sequence[object],
    artifact_store: ArtifactStore,
) -> None:
    """Fail closed before any DB write if valuation surfaces disagree."""
    if source not in PRODUCTION_VALUATION_SOURCES:
        return
    snapshots = [record for record in records if isinstance(record, Snapshot)]
    positions = [record for record in records if isinstance(record, Position)]
    # Find the snapshot matching manifest (exactly one required).
    target = [snap for snap in snapshots if snap.snapshot_id == manifest.snapshot_id]
    if len(target) != 1:
        raise _import_error(
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
            raise _import_error(
                "valuation_status_mismatch: "
                f"{position.position_id} stored={position.valuation_status} "
                f"derived={assessment.status.value}"
            )
        if assessment.policy_id != BASE_VALUATION_POLICY_V1.policy_id:
            raise _import_error("valuation_policy_mismatch")

    # --- Findings agreement ---
    expected_valuation: list[tuple] = []
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
        raise _import_error(
            f"valuation_receipt_mismatch: cannot read receipt artifact: {exc}"
        ) from exc
    receipt_findings = list(receipt_payload.get("findings") or [])
    receipt_valuation = [
        _normalize_tuple(f) for f in receipt_findings if _is_valuation_finding(f)
    ]

    if Counter(batch_valuation) != expected_counter:
        raise _import_error(
            "valuation_findings_mismatch: batch findings diverge from "
            f"canonical assessment batch={batch_valuation} expected={expected_valuation}"
        )
    if Counter(snap_valuation) != expected_counter:
        raise _import_error(
            "valuation_snapshot_mismatch: snapshot findings diverge from "
            f"canonical assessment snap={snap_valuation} expected={expected_valuation}"
        )
    if Counter(receipt_valuation) != expected_counter:
        raise _import_error(
            "valuation_receipt_mismatch: receipt findings diverge from "
            f"canonical assessment receipt={receipt_valuation} expected={expected_valuation}"
        )

    # --- Completeness agreement ---
    expected_completeness = completeness_status(
        [
            ImportFinding(
                code=str(_as_finding_dict(f).get("code") or ""),
                severity=_as_finding_dict(f).get("severity") or "partial",
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
        raise _import_error(
            "valuation_completeness_mismatch: "
            f"batch={batch.completeness_status} snapshot={snap_completeness} "
            f"receipt={receipt_completeness} expected={expected_completeness}"
        )

    # --- Record-count consistency (all four surfaces, full dict) ---
    batch_counts = dict(batch.record_counts)
    manifest_counts = dict(manifest.record_counts)
    snap_counts = dict((snapshot.payload or {}).get("record_counts") or {})
    receipt_counts = dict(receipt_payload.get("record_counts") or {})

    if manifest_counts != batch_counts:
        raise _import_error(
            "valuation_record_count_mismatch: manifest counts "
            f"{manifest_counts} != batch {batch_counts}"
        )
    if snap_counts != batch_counts:
        raise _import_error(
            "valuation_record_count_mismatch: snapshot payload counts "
            f"{snap_counts} != batch {batch_counts}"
        )
    if receipt_counts != batch_counts:
        raise _import_error(
            "valuation_record_count_mismatch: receipt payload counts "
            f"{receipt_counts} != batch {batch_counts}"
        )

    # Verify position count from records matches declared count.
    actual_position_count = len(positions)
    if batch_counts.get("position", 0) != actual_position_count:
        raise _import_error(
            f"valuation_position_count: batch declares "
            f"{batch_counts.get('position', 0)} positions but {actual_position_count} present"
        )

    # Verify exactly one Snapshot present (all production sources).
    if len(snapshots) != 1:
        raise _import_error(
            "valuation_snapshot_count: expected exactly one Snapshot "
            f"for source {source}, got {len(snapshots)}"
        )

    # Verify declared record_counts against actual records for known class keys.
    actual_by_class: dict[str, int] = {}
    for record in records:
        cls_name = type(record).__name__
        actual_by_class[cls_name] = actual_by_class.get(cls_name, 0) + 1
    for key, cls_name in _RECORD_COUNT_KEY_TO_CLASS.items():
        actual = actual_by_class.get(cls_name, 0)
        if key in _DIRECT_SOURCE_DOMAIN_KEYS:
            declared = batch_counts.get(key, 0)
        else:
            if key not in batch_counts:
                continue
            declared = batch_counts[key]
        if declared != actual:
            raise _import_error(
                f"valuation_record_count_mismatch: batch.{key}="
                f"{declared} actual={actual} (class {cls_name})"
            )

    # Verify every Position binds the manifest snapshot.
    wrong_binding = [
        p.position_id for p in positions
        if p.snapshot_id != manifest.snapshot_id
    ]
    if wrong_binding:
        raise _import_error(
            "valuation_snapshot_binding: positions bound to wrong snapshot "
            f"expected={manifest.snapshot_id} wrong={wrong_binding}"
        )

    # --- Valuation assessment surface agreement (policy, clock, status_counts) ---
    canonical_status_counts: dict[str, int] = {}
    for assessment in assessments:
        s = assessment.status.value
        canonical_status_counts[s] = canonical_status_counts.get(s, 0) + 1

    snap_assessment = (snapshot.payload or {}).get("valuation_assessment") or {}
    receipt_assessment = receipt_payload.get("valuation_assessment") or {}
    canonical_policy = BASE_VALUATION_POLICY_V1.policy_id
    for label, source_assessment in [
        ("snapshot", snap_assessment),
        ("receipt", receipt_assessment),
    ]:
        if source_assessment.get("policy_id") != canonical_policy:
            raise _import_error(
                "valuation_policy_mismatch: "
                f"{label} policy={source_assessment.get('policy_id')} "
                f"expected={canonical_policy}"
            )
        if source_assessment.get("evaluated_at_utc") != observed:
            raise _import_error(
                "valuation_policy_mismatch: "
                f"{label} evaluated_at="
                f"{source_assessment.get('evaluated_at_utc')} "
                f"expected={observed}"
            )
        if source_assessment.get("status_counts") != canonical_status_counts:
            raise _import_error(
                "valuation_status_counts_mismatch: "
                f"{label} status_counts={source_assessment.get('status_counts')} "
                f"canonical={canonical_status_counts}"
            )
