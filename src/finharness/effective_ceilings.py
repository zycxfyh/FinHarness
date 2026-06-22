"""Governed ceiling resolution for human-owned risk caps.

Ceilings are maximums owned by governance evidence, not by a request. A request
may tighten a cap for one run, but it may not raise the effective ceiling unless
there is lineage from a traceable rule change or an explicit control-owner
certification receipt.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from finharness.control_owner import (
    CONTROL_CERTIFICATION_STATE_ROOT,
    ControlCertification,
)
from finharness.rule_change_ledger import (
    RULE_CHANGE_STATE_ROOT,
    RuleChange,
    is_traceable,
)

CEILING_TARGET_PREFIX = "ceiling."


class CeilingResolutionError(RuntimeError):
    """Raised when a ceiling source cannot be safely interpreted."""


@dataclass(frozen=True)
class CeilingProvenance:
    """One accepted source that set an effective ceiling."""

    source_type: Literal["rule_change", "control_owner_certification"]
    source_id: str
    value: float
    created_at_utc: str
    attester: str
    target: str

    def as_receipt_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EffectiveCeiling:
    """Resolved ceiling plus evidence about what was accepted or ignored."""

    field: str
    configured_ceiling: float
    effective_ceiling: float
    provenance: CeilingProvenance | None
    ignored: list[str]

    def as_receipt_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "configured_ceiling": self.configured_ceiling,
            "effective_ceiling": self.effective_ceiling,
            "provenance": (
                self.provenance.as_receipt_dict()
                if self.provenance is not None
                else None
            ),
            "ignored": list(self.ignored),
        }


@dataclass(frozen=True)
class EnforcedCap:
    """A request cap clamped against an effective human-owned ceiling."""

    field: str
    configured_ceiling: float
    effective_ceiling: float
    request_limit: float
    enforced_cap: float
    request_limit_clamped_to_ceiling: bool
    cap_invariant_holds: bool
    provenance: CeilingProvenance | None
    ignored: list[str]

    def as_receipt_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "configured_ceiling": self.configured_ceiling,
            "effective_ceiling": self.effective_ceiling,
            "request_limit": self.request_limit,
            "enforced_cap": self.enforced_cap,
            "request_limit_clamped_to_ceiling": self.request_limit_clamped_to_ceiling,
            "cap_invariant_holds": self.cap_invariant_holds,
            "provenance": (
                self.provenance.as_receipt_dict()
                if self.provenance is not None
                else None
            ),
            "ignored": list(self.ignored),
        }


@dataclass(frozen=True)
class _Candidate:
    value: float
    provenance: CeilingProvenance


def _bounded_positive(value: Any) -> float | None:
    try:
        bounded = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(bounded) or bounded <= 0:
        return None
    return bounded


def _target_for(field: str) -> str:
    clean = field.strip()
    if not clean:
        raise CeilingResolutionError("ceiling field must be non-empty")
    return clean if clean.startswith(CEILING_TARGET_PREFIX) else f"{CEILING_TARGET_PREFIX}{clean}"


def _display_field(field: str) -> str:
    return field[len(CEILING_TARGET_PREFIX) :] if field.startswith(CEILING_TARGET_PREFIX) else field


def _load_rule_changes_strict(state_root: Path | None) -> list[RuleChange]:
    state = state_root or RULE_CHANGE_STATE_ROOT
    if not state.is_dir():
        return []
    changes: list[RuleChange] = []
    for path in sorted(state.glob("rulechg_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            changes.append(RuleChange.model_validate(payload))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise CeilingResolutionError(
                f"rule-change source unreadable for ceiling resolution: {path}: {exc}"
            ) from exc
    return changes


def _load_certifications_strict(state_root: Path | None) -> list[ControlCertification]:
    state = state_root or CONTROL_CERTIFICATION_STATE_ROOT
    if not state.is_dir():
        return []
    certifications: list[ControlCertification] = []
    for path in sorted(state.glob("ctrlcert_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            certifications.append(ControlCertification.model_validate(payload))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise CeilingResolutionError(
                "control-owner certification source unreadable for ceiling "
                f"resolution: {path}: {exc}"
            ) from exc
    return certifications


def _owner_authorized_value(
    certification: ControlCertification,
    *,
    field: str,
    target: str,
) -> float | None:
    authorized = certification.authorized_ceilings
    if target in authorized:
        return _bounded_positive(authorized[target])
    if field in authorized:
        return _bounded_positive(authorized[field])
    return None


def resolve_effective_ceiling(
    *,
    field: str,
    default_ceiling: float,
    rule_changes: list[RuleChange] | None = None,
    owner_certs: list[ControlCertification] | None = None,
    rule_change_root: Path | None = None,
    certification_root: Path | None = None,
) -> EffectiveCeiling:
    """Return a ceiling resolved only from governed, traceable sources.

    The accepted namespace is ``ceiling.<field>``. Guard thresholds remain in
    ``guard.*`` and are deliberately ignored here.
    """
    configured = _bounded_positive(default_ceiling)
    if configured is None:
        raise CeilingResolutionError("default ceiling must be a positive finite number")

    target = _target_for(field)
    display_field = _display_field(target)
    changes = (
        list(rule_changes)
        if rule_changes is not None
        else _load_rule_changes_strict(rule_change_root)
    )
    certifications = (
        list(owner_certs)
        if owner_certs is not None
        else _load_certifications_strict(certification_root)
    )
    candidates: list[_Candidate] = []
    ignored: list[str] = []

    for change in changes:
        if not change.rule_target.startswith(CEILING_TARGET_PREFIX):
            continue
        if change.rule_target != target:
            continue
        value = _bounded_positive(change.new_value)
        if (
            change.change_kind != "threshold"
            or change.status != "active"
            or value is None
            or not is_traceable(change)
        ):
            ignored.append(change.rule_change_id)
            continue
        candidates.append(
            _Candidate(
                value=value,
                provenance=CeilingProvenance(
                    source_type="rule_change",
                    source_id=change.rule_change_id,
                    value=value,
                    created_at_utc=change.created_at_utc,
                    attester=change.attester,
                    target=change.rule_target,
                ),
            )
        )

    for certification in certifications:
        value = _owner_authorized_value(
            certification,
            field=display_field,
            target=target,
        )
        if value is None:
            continue
        if certification.status != "certified" or not certification.baseline_passed:
            ignored.append(certification.certification_id)
            continue
        candidates.append(
            _Candidate(
                value=value,
                provenance=CeilingProvenance(
                    source_type="control_owner_certification",
                    source_id=certification.certification_id,
                    value=value,
                    created_at_utc=certification.created_at_utc,
                    attester=certification.control_owner,
                    target=target,
                ),
            )
        )

    if candidates:
        # Latest evidence wins, mirroring effective_rules' "latest change wins"
        # posture while permitting owner certifications and rule changes to share
        # one ordering.
        selected = max(
            candidates,
            key=lambda item: (
                item.provenance.created_at_utc,
                item.provenance.source_id,
            ),
        )
        return EffectiveCeiling(
            field=display_field,
            configured_ceiling=configured,
            effective_ceiling=selected.value,
            provenance=selected.provenance,
            ignored=ignored,
        )

    return EffectiveCeiling(
        field=display_field,
        configured_ceiling=configured,
        effective_ceiling=configured,
        provenance=None,
        ignored=ignored,
    )


def enforce_request_limit(
    *,
    field: str,
    default_ceiling: float,
    request_limit: float | None,
    rule_change_root: Path | None = None,
    certification_root: Path | None = None,
) -> EnforcedCap:
    """Clamp a request limit against the resolved effective ceiling."""
    ceiling = resolve_effective_ceiling(
        field=field,
        default_ceiling=default_ceiling,
        rule_change_root=rule_change_root,
        certification_root=certification_root,
    )
    bounded_request = (
        ceiling.effective_ceiling
        if request_limit is None
        else _bounded_positive(request_limit)
    )
    if bounded_request is None:
        raise CeilingResolutionError(
            f"request limit for {ceiling.field} must be a positive finite number"
        )
    enforced = min(bounded_request, ceiling.effective_ceiling)
    return EnforcedCap(
        field=ceiling.field,
        configured_ceiling=ceiling.configured_ceiling,
        effective_ceiling=ceiling.effective_ceiling,
        request_limit=bounded_request,
        enforced_cap=enforced,
        request_limit_clamped_to_ceiling=bounded_request > ceiling.effective_ceiling,
        cap_invariant_holds=enforced <= ceiling.effective_ceiling,
        provenance=ceiling.provenance,
        ignored=ceiling.ignored,
    )
