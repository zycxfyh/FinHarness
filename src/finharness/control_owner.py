"""Control-owner certification receipts for FinHarness safety brakes.

This module mirrors the rule-change ledger shape: a named human attests, the
project writes a dated receipt, and the record stays evidence rather than
authority. It does not modify risk, execution, or trading controls.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.market_data import ROOT

CONTROL_CERTIFICATION_STATE_ROOT = ROOT / "data" / "state" / "control-certifications"
CONTROL_CERTIFICATION_RECEIPT_ROOT = ROOT / "data" / "receipts" / "control-certifications"

CONTROL_BASELINE_INVARIANTS = [
    "INV-1: AI never places orders directly; non-live is the default.",
    "INV-2: Live execution is blocked before submit.",
    "INV-3: Human attestation is fail-closed.",
    "INV-4: risk_gate retains mandate, permission, cap, and no-live authority.",
    "INV-5: Behavior stops still trip.",
    "INV-6: Lesson-to-rule changes are refused without lineage.",
    "INV-7: Receipts separate claim, evidence, and non-claim.",
    "INV-8: New wheels emit evidence, never authority.",
]

CONTROL_BASELINE_TEST_MODULES = [
    "tests.test_execution",
    "tests.test_risk_gate",
    "tests.test_risk_gate_interrupt",
    "tests.test_hardening_gate",
    "tests.test_post_trade",
]

NON_CERTIFICATION_STATEMENT = (
    "This is a local control-owner attestation that the project's safety "
    "invariants were tested on this date. It is not SEC/FINRA/legal compliance "
    "certification, not a release approval, and not live-trading authorization."
)


class ControlCertificationError(RuntimeError):
    """Raised when control certification cannot be attempted."""


class ControlCertification(BaseModel):
    """A dated control-owner certification or non-certification record."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "finharness.control_certification.v1"
    certification_id: str
    created_at_utc: str
    control_owner: str
    review_cadence_days: int
    next_review_due_utc: str
    controls_in_force: list[str] = Field(default_factory=list)
    baseline_passed: bool
    baseline_evidence: dict[str, Any]
    status: Literal["certified", "not_certified"]
    non_certification_statement: str = NON_CERTIFICATION_STATEMENT


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def certify_controls(
    *,
    control_owner: str,
    review_cadence_days: int,
    baseline_passed: bool,
    baseline_evidence: dict[str, Any],
    controls_in_force: list[str] | None = None,
    state_root: Path | None = None,
    receipt_root: Path | None = None,
    created_at_utc: str | None = None,
) -> ControlCertification:
    """Record a human control-owner certification attempt.

    A failed baseline is still recorded, but its status is ``not_certified``.
    Missing owner identity is refused before any receipt is written.
    """
    owner = control_owner.strip()
    if not owner:
        raise ControlCertificationError(
            "certification requires a named human control owner"
        )
    if review_cadence_days <= 0:
        raise ControlCertificationError("review cadence must be positive")

    created_at = created_at_utc or _now_utc()
    next_due = _parse_utc(created_at) + timedelta(days=review_cadence_days)
    stamp = _parse_utc(created_at).strftime("%Y%m%dT%H%M%SZ")
    certification = ControlCertification(
        certification_id=f"ctrlcert_{stamp}_{uuid4().hex[:8]}",
        created_at_utc=created_at,
        control_owner=owner,
        review_cadence_days=review_cadence_days,
        next_review_due_utc=next_due.isoformat(),
        controls_in_force=controls_in_force or list(CONTROL_BASELINE_INVARIANTS),
        baseline_passed=baseline_passed,
        baseline_evidence=baseline_evidence,
        status="certified" if baseline_passed else "not_certified",
    )

    state = state_root or CONTROL_CERTIFICATION_STATE_ROOT
    receipts = receipt_root or CONTROL_CERTIFICATION_RECEIPT_ROOT
    payload = certification.model_dump(mode="json")
    _write_json(state / f"{certification.certification_id}.json", payload)
    _write_json(
        receipts / f"receipt_{certification.certification_id}.json",
        {
            "receipt_id": f"receipt_{certification.certification_id}",
            "kind": "control_owner_certification",
            "created_at_utc": certification.created_at_utc,
            "certification": payload,
            "lineage": {
                "baseline_test_modules": baseline_evidence.get("test_modules", []),
                "baseline_returncode": baseline_evidence.get("returncode"),
                "control_count": len(certification.controls_in_force),
            },
            "not_claimed": [
                "Not legal or regulatory compliance certification.",
                "Not release approval.",
                "Not live-trading authorization.",
            ],
        },
    )
    return certification


def load_certifications(state_root: Path | None = None) -> list[ControlCertification]:
    state = state_root or CONTROL_CERTIFICATION_STATE_ROOT
    if not state.is_dir():
        return []
    certifications: list[ControlCertification] = []
    for path in sorted(state.glob("ctrlcert_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            certifications.append(ControlCertification.model_validate(payload))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return certifications


def latest_certification(
    state_root: Path | None = None,
) -> ControlCertification | None:
    certifications = load_certifications(state_root)
    if not certifications:
        return None
    return max(certifications, key=lambda item: item.created_at_utc)


def audit_overdue(
    *,
    now_utc: str | None = None,
    state_root: Path | None = None,
) -> list[str]:
    now = _parse_utc(now_utc or _now_utc())
    return [
        certification.certification_id
        for certification in load_certifications(state_root)
        if _parse_utc(certification.next_review_due_utc) < now
    ]
