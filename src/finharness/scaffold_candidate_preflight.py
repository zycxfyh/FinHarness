"""System-recomputed preflight for Agent scaffold revision candidates.

The Agent candidate payload can suggest ``preflight_result`` and ``risk_coverage``,
but those fields are review material, not system truth. This module recomputes the
minimal pre-apply checks from current proposal state, active risk register state,
and the candidate review event payload without mutating state.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.risk_register import read_review_risk_register
from finharness.statecore.decision_scaffold import (
    ALL_FIELDS,
    DecisionScaffoldError,
    ensure_forcing,
    normalize,
)
from finharness.statecore.models import Proposal, ReviewEvent

PreflightStatus = Literal["pass", "warn", "block"]
PreflightSeverity = Literal["info", "warning", "blocking"]

SCAFFOLD_CANDIDATE_PREFLIGHT_NON_CLAIMS: tuple[str, ...] = (
    "System preflight is a deterministic review check, not approval.",
    "System preflight does not apply a candidate or mutate proposal state.",
    "System preflight is not investment advice or execution authorization.",
)

_FORBIDDEN_AUTHORITY_FIELDS = frozenset(
    {
        "execution_allowed",
        "authority_transition",
        "approval_status",
        "approval",
        "decision",
        "approve",
        "approved",
        "rejection",
        "reject",
        "rejected",
        "attestation",
        "attestation_ref",
    }
)


@dataclass(frozen=True)
class ScaffoldCandidateRecord:
    event: ReviewEvent
    payload: dict[str, Any] | None
    candidate_receipt_ref: str | None
    payload_error: str | None = None


@dataclass(frozen=True)
class PreflightFinding:
    code: str
    severity: PreflightSeverity
    message: str
    recovery_hint: str
    source_refs: list[str]
    receipt_refs: list[str]
    blocks_apply: bool


@dataclass(frozen=True)
class ScaffoldCandidatePreflightReport:
    candidate_id: str
    proposal_id: str
    status: PreflightStatus
    system_preflight_recomputed: bool
    findings: list[PreflightFinding]
    candidate_receipt_ref: str | None
    current_proposal_receipt_ref: str | None
    proposed_scaffold: dict[str, Any]
    changed_fields: list[str]
    basis_risk_ids: list[str]
    active_basis_risk_ids: list[str]
    missing_basis_risk_ids: list[str]
    source_refs: list[str]
    receipt_refs: list[str]
    report_hash: str
    non_claims: tuple[str, ...] = SCAFFOLD_CANDIDATE_PREFLIGHT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


def candidate_receipt_ref(event: ReviewEvent) -> str | None:
    suffix = f"review-events/receipt_{event.review_event_id}.json"
    for ref in event.source_refs:
        if str(ref).endswith(suffix):
            return str(ref)
    return None


def find_scaffold_revision_candidate(
    candidate_id: str,
    *,
    engine: Engine,
) -> ScaffoldCandidateRecord | None:
    """Find a scaffold candidate review event and parse its payload when possible."""

    with Session(engine) as session:
        events = list(
            session.exec(
                select(ReviewEvent).where(
                    ReviewEvent.kind == "agent_scaffold_revision_apply_candidate"
                )
            ).all()
        )
    for event in events:
        text = event.text or ""
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            if "candidate_id" in text and candidate_id in text:
                return ScaffoldCandidateRecord(
                    event=event,
                    payload=None,
                    candidate_receipt_ref=candidate_receipt_ref(event),
                    payload_error="candidate payload is unreadable",
                )
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("candidate_id") == candidate_id:
            return ScaffoldCandidateRecord(
                event=event,
                payload=payload,
                candidate_receipt_ref=candidate_receipt_ref(event),
            )
    return None


def preflight_scaffold_revision_candidate(
    candidate_id: str,
    *,
    engine: Engine,
    receipt_root: Path,
) -> ScaffoldCandidatePreflightReport | None:
    """Recompute pre-apply checks for an Agent scaffold revision candidate."""

    record = find_scaffold_revision_candidate(candidate_id, engine=engine)
    if record is None:
        return None

    proposal = _proposal(record.event.proposal_id, engine=engine)
    payload = record.payload
    findings: list[PreflightFinding] = []
    proposed_scaffold: dict[str, Any] = {}
    changed_fields: list[str] = []
    basis_risk_ids: list[str] = []
    active_basis_risk_ids: list[str] = []
    missing_basis_risk_ids: list[str] = []

    source_refs = _dedupe(
        [
            *record.event.source_refs,
            *(_string_list(payload.get("source_refs")) if payload else []),
        ]
    )
    receipt_refs = _dedupe(
        [
            *(source_refs if record.candidate_receipt_ref is None else []),
            *([record.candidate_receipt_ref] if record.candidate_receipt_ref else []),
            *([proposal.receipt_ref] if proposal and proposal.receipt_ref else []),
            *(_string_list(payload.get("receipt_refs")) if payload else []),
        ]
    )

    if record.candidate_receipt_ref is None:
        findings.append(
            _finding(
                code="missing_candidate_receipt_ref",
                severity="blocking",
                message="Candidate review event does not expose its receipt reference.",
                recovery_hint="Regenerate the candidate so its review-event receipt is indexed.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )

    if proposal is None:
        findings.append(
            _finding(
                code="proposal_missing",
                severity="blocking",
                message="Candidate references a proposal that no longer exists in state core.",
                recovery_hint="Recreate or discard the candidate after restoring proposal state.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )

    if record.payload_error is not None or payload is None:
        findings.append(
            _finding(
                code="candidate_payload_unreadable",
                severity="blocking",
                message=record.payload_error or "Candidate payload is not an object.",
                recovery_hint="Regenerate the candidate from current review context.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
        return _report(
            candidate_id=candidate_id,
            proposal_id=record.event.proposal_id,
            findings=findings,
            candidate_receipt_ref=record.candidate_receipt_ref,
            current_proposal_receipt_ref=proposal.receipt_ref if proposal else None,
            proposed_scaffold=proposed_scaffold,
            changed_fields=changed_fields,
            basis_risk_ids=basis_risk_ids,
            active_basis_risk_ids=active_basis_risk_ids,
            missing_basis_risk_ids=missing_basis_risk_ids,
            source_refs=source_refs,
            receipt_refs=receipt_refs,
        )

    findings.extend(
        _payload_findings(
            payload=payload,
            event=record.event,
            proposal=proposal,
            source_refs=source_refs,
            receipt_refs=receipt_refs,
        )
    )

    if proposal is not None:
        proposal_receipt = proposal.receipt_ref or None
        previous_receipt = _previous_proposal_receipt(payload)
        if previous_receipt is None:
            findings.append(
                _finding(
                    code="missing_candidate_base_receipt",
                    severity="warning",
                    message="Candidate does not declare the proposal receipt it was based on.",
                    recovery_hint=(
                        "Regenerate the candidate with "
                        "rollback_info.previous_proposal_receipt_ref."
                    ),
                    source_refs=source_refs,
                    receipt_refs=receipt_refs,
                    blocks_apply=False,
                )
            )
        elif previous_receipt != proposal_receipt:
            findings.append(
                _finding(
                    code="stale_proposal_receipt",
                    severity="blocking",
                    message="Candidate was prepared against an older proposal receipt.",
                    recovery_hint="Regenerate the candidate from the current proposal state.",
                    source_refs=source_refs,
                    receipt_refs=receipt_refs,
                )
            )

        scaffold_result = _recompute_scaffold(
            payload=payload,
            proposal=proposal,
            source_refs=source_refs,
            receipt_refs=receipt_refs,
        )
        proposed_scaffold = scaffold_result[0]
        changed_fields = scaffold_result[1]
        findings.extend(scaffold_result[2])

        risk_result = _basis_risk_findings(
            payload=payload,
            proposal_id=proposal.proposal_id,
            engine=engine,
            receipt_root=receipt_root,
            source_refs=source_refs,
            receipt_refs=receipt_refs,
        )
        basis_risk_ids = risk_result[0]
        active_basis_risk_ids = risk_result[1]
        missing_basis_risk_ids = risk_result[2]
        findings.extend(risk_result[3])

    return _report(
        candidate_id=candidate_id,
        proposal_id=record.event.proposal_id,
        findings=findings,
        candidate_receipt_ref=record.candidate_receipt_ref,
        current_proposal_receipt_ref=proposal.receipt_ref if proposal else None,
        proposed_scaffold=proposed_scaffold,
        changed_fields=changed_fields,
        basis_risk_ids=basis_risk_ids,
        active_basis_risk_ids=active_basis_risk_ids,
        missing_basis_risk_ids=missing_basis_risk_ids,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
    )


def _proposal(proposal_id: str, *, engine: Engine) -> Proposal | None:
    with Session(engine) as session:
        return session.get(Proposal, proposal_id)


def _payload_findings(
    *,
    payload: dict[str, Any],
    event: ReviewEvent,
    proposal: Proposal | None,
    source_refs: list[str],
    receipt_refs: list[str],
) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    if payload.get("proposal_id") != event.proposal_id:
        findings.append(
            _finding(
                code="candidate_proposal_mismatch",
                severity="blocking",
                message="Candidate payload proposal_id does not match the review event.",
                recovery_hint="Discard this candidate and regenerate it for the target proposal.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    if proposal is not None and payload.get("proposal_id") != proposal.proposal_id:
        findings.append(
            _finding(
                code="candidate_current_proposal_mismatch",
                severity="blocking",
                message="Candidate payload does not match the current proposal.",
                recovery_hint="Regenerate the candidate from the current proposal.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    marker = _contains_forbidden_authority_marker(payload)
    if marker is not None:
        findings.append(
            _finding(
                code="forbidden_authority_marker",
                severity="blocking",
                message=f"Candidate payload carries forbidden authority marker {marker!r}.",
                recovery_hint=(
                    "Regenerate the candidate without approval, decision, "
                    "or execution fields."
                ),
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    return findings


def _recompute_scaffold(
    *,
    payload: dict[str, Any],
    proposal: Proposal,
    source_refs: list[str],
    receipt_refs: list[str],
) -> tuple[dict[str, Any], list[str], list[PreflightFinding]]:
    findings: list[PreflightFinding] = []
    patch = payload.get("scaffold_patch")
    if not isinstance(patch, dict):
        return {}, [], [
            _finding(
                code="candidate_scaffold_patch_invalid",
                severity="blocking",
                message="Candidate scaffold_patch is not an object.",
                recovery_hint="Regenerate the candidate with an object scaffold_patch.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        ]
    unknown = sorted(set(patch) - set(ALL_FIELDS))
    if unknown:
        findings.append(
            _finding(
                code="unknown_scaffold_fields",
                severity="blocking",
                message="Candidate scaffold_patch has unknown field(s): " + ", ".join(unknown),
                recovery_hint="Use only the governed decision scaffold fields.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    normalized_patch = normalize(patch)
    if not normalized_patch:
        findings.append(
            _finding(
                code="empty_scaffold_patch",
                severity="blocking",
                message="Candidate scaffold_patch has no non-blank governed fields.",
                recovery_hint="Regenerate the candidate with at least one scaffold change.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    previous_scaffold = normalize(proposal.decision_scaffold)
    try:
        proposed_scaffold = ensure_forcing({**previous_scaffold, **normalized_patch})
    except DecisionScaffoldError as exc:
        return {}, [], [
            *findings,
            _finding(
                code="scaffold_forcing_failed",
                severity="blocking",
                message=str(exc),
                recovery_hint="Regenerate the candidate after restoring required scaffold fields.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            ),
        ]
    changed_fields = [
        field
        for field in ALL_FIELDS
        if previous_scaffold.get(field) != proposed_scaffold.get(field)
    ]
    if not changed_fields:
        findings.append(
            _finding(
                code="noop_scaffold_patch",
                severity="blocking",
                message="System preflight found no scaffold fields changed by this candidate.",
                recovery_hint="Discard the candidate or regenerate it with a real scaffold change.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    _compare_candidate_scaffold(
        payload=payload,
        proposed_scaffold=proposed_scaffold,
        changed_fields=changed_fields,
        findings=findings,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
    )
    return proposed_scaffold, changed_fields, findings


def _compare_candidate_scaffold(
    *,
    payload: dict[str, Any],
    proposed_scaffold: dict[str, Any],
    changed_fields: list[str],
    findings: list[PreflightFinding],
    source_refs: list[str],
    receipt_refs: list[str],
) -> None:
    candidate_proposed = payload.get("proposed_scaffold")
    if not isinstance(candidate_proposed, dict):
        findings.append(
            _finding(
                code="candidate_proposed_scaffold_missing",
                severity="blocking",
                message="Candidate does not carry an object proposed_scaffold.",
                recovery_hint="Regenerate the candidate from current proposal state.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    elif normalize(candidate_proposed) != proposed_scaffold:
        findings.append(
            _finding(
                code="candidate_proposed_scaffold_mismatch",
                severity="blocking",
                message="Candidate proposed_scaffold does not match system recomputation.",
                recovery_hint="Regenerate the candidate from current proposal state.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    candidate_changed = _string_list(payload.get("changed_fields"))
    if candidate_changed != changed_fields:
        findings.append(
            _finding(
                code="candidate_changed_fields_mismatch",
                severity="blocking",
                message="Candidate changed_fields do not match system recomputation.",
                recovery_hint="Regenerate the candidate from current proposal state.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )


def _basis_risk_findings(
    *,
    payload: dict[str, Any],
    proposal_id: str,
    engine: Engine,
    receipt_root: Path,
    source_refs: list[str],
    receipt_refs: list[str],
) -> tuple[list[str], list[str], list[str], list[PreflightFinding]]:
    findings: list[PreflightFinding] = []
    basis_risk_ids = _dedupe(_string_list(payload.get("basis_risk_ids")))
    register = read_review_risk_register(
        engine,
        receipt_root=receipt_root,
        limit=500,
        include_closed=False,
    )
    active_risks = {item.risk_id: item for item in register.items}
    active_basis_risk_ids = [
        risk_id
        for risk_id in basis_risk_ids
        if risk_id in active_risks and proposal_id in active_risks[risk_id].related_proposal_ids
    ]
    missing_basis_risk_ids = [
        risk_id for risk_id in basis_risk_ids if risk_id not in active_basis_risk_ids
    ]
    if not basis_risk_ids:
        findings.append(
            _finding(
                code="missing_basis_risks",
                severity="blocking",
                message="Candidate does not declare basis_risk_ids.",
                recovery_hint="Regenerate the candidate from active risk register items.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    elif missing_basis_risk_ids:
        findings.append(
            _finding(
                code="inactive_or_unrelated_basis_risks",
                severity="blocking",
                message="Candidate basis risk(s) are no longer active for this proposal.",
                recovery_hint="Refresh the risk register and regenerate the candidate.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    coverage = payload.get("risk_coverage")
    addressed = _string_list(coverage.get("addressed")) if isinstance(coverage, dict) else []
    uncovered = [risk_id for risk_id in basis_risk_ids if risk_id not in addressed]
    if uncovered:
        findings.append(
            _finding(
                code="risk_coverage_incomplete",
                severity="warning",
                message="Candidate risk_coverage does not address every basis risk.",
                recovery_hint=(
                    "Ask the Agent to refresh risk_coverage or document why "
                    "coverage is partial."
                ),
                source_refs=source_refs,
                receipt_refs=receipt_refs,
                blocks_apply=False,
            )
        )
    return basis_risk_ids, active_basis_risk_ids, missing_basis_risk_ids, findings


def _previous_proposal_receipt(payload: dict[str, Any]) -> str | None:
    rollback_info = payload.get("rollback_info")
    if not isinstance(rollback_info, dict):
        return None
    value = rollback_info.get("previous_proposal_receipt_ref")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _contains_forbidden_authority_marker(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in {"execution_allowed", "authority_transition"} and child is False:
                continue
            if normalized in _FORBIDDEN_AUTHORITY_FIELDS:
                return normalized
            if (marker := _contains_forbidden_authority_marker(child)) is not None:
                return marker
    if isinstance(value, (list, tuple)):
        for child in value:
            if (marker := _contains_forbidden_authority_marker(child)) is not None:
                return marker
    return None


def _finding(
    *,
    code: str,
    severity: PreflightSeverity,
    message: str,
    recovery_hint: str,
    source_refs: list[str],
    receipt_refs: list[str],
    blocks_apply: bool = True,
) -> PreflightFinding:
    return PreflightFinding(
        code=code,
        severity=severity,
        message=message,
        recovery_hint=recovery_hint,
        source_refs=list(source_refs),
        receipt_refs=list(receipt_refs),
        blocks_apply=blocks_apply,
    )


def _report(
    *,
    candidate_id: str,
    proposal_id: str,
    findings: list[PreflightFinding],
    candidate_receipt_ref: str | None,
    current_proposal_receipt_ref: str | None,
    proposed_scaffold: dict[str, Any],
    changed_fields: list[str],
    basis_risk_ids: list[str],
    active_basis_risk_ids: list[str],
    missing_basis_risk_ids: list[str],
    source_refs: list[str],
    receipt_refs: list[str],
) -> ScaffoldCandidatePreflightReport:
    status: PreflightStatus
    if any(finding.blocks_apply for finding in findings):
        status = "block"
    elif findings:
        status = "warn"
    else:
        status = "pass"
    report_hash = _report_hash(
        candidate_id=candidate_id,
        proposal_id=proposal_id,
        status=status,
        findings=findings,
        candidate_receipt_ref=candidate_receipt_ref,
        current_proposal_receipt_ref=current_proposal_receipt_ref,
        proposed_scaffold=proposed_scaffold,
        changed_fields=changed_fields,
        basis_risk_ids=basis_risk_ids,
        active_basis_risk_ids=active_basis_risk_ids,
        missing_basis_risk_ids=missing_basis_risk_ids,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
    )
    return ScaffoldCandidatePreflightReport(
        candidate_id=candidate_id,
        proposal_id=proposal_id,
        status=status,
        system_preflight_recomputed=True,
        findings=findings,
        candidate_receipt_ref=candidate_receipt_ref,
        current_proposal_receipt_ref=current_proposal_receipt_ref,
        proposed_scaffold=proposed_scaffold,
        changed_fields=changed_fields,
        basis_risk_ids=basis_risk_ids,
        active_basis_risk_ids=active_basis_risk_ids,
        missing_basis_risk_ids=missing_basis_risk_ids,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
        report_hash=report_hash,
        execution_allowed=False,
        authority_transition=False,
    )


def _report_hash(
    *,
    candidate_id: str,
    proposal_id: str,
    status: str,
    findings: list[PreflightFinding],
    candidate_receipt_ref: str | None,
    current_proposal_receipt_ref: str | None,
    proposed_scaffold: dict[str, Any],
    changed_fields: list[str],
    basis_risk_ids: list[str],
    active_basis_risk_ids: list[str],
    missing_basis_risk_ids: list[str],
    source_refs: list[str],
    receipt_refs: list[str],
) -> str:
    payload = {
        "candidate_id": candidate_id,
        "proposal_id": proposal_id,
        "status": status,
        "system_preflight_recomputed": True,
        "findings": [
            {
                "code": finding.code,
                "severity": finding.severity,
                "message": finding.message,
                "recovery_hint": finding.recovery_hint,
                "source_refs": finding.source_refs,
                "receipt_refs": finding.receipt_refs,
                "blocks_apply": finding.blocks_apply,
            }
            for finding in findings
        ],
        "candidate_receipt_ref": candidate_receipt_ref,
        "current_proposal_receipt_ref": current_proposal_receipt_ref,
        "proposed_scaffold": proposed_scaffold,
        "changed_fields": changed_fields,
        "basis_risk_ids": basis_risk_ids,
        "active_basis_risk_ids": active_basis_risk_ids,
        "missing_basis_risk_ids": missing_basis_risk_ids,
        "source_refs": source_refs,
        "receipt_refs": receipt_refs,
        "execution_allowed": False,
        "authority_transition": False,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})
