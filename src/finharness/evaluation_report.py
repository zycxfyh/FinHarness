"""EvaluationReport v0 — common projection for local evaluators.

Agentic-space dimension: Evaluation Space.

Unifies the output shape of local evaluators (scaffold preflight,
proposal queue checks, etc.) into a common EvaluationReport with
a fixed status (pass/warn/block) and structured findings.

This is a projection layer — it does not replace existing evaluator
models. It adapts their outputs into a shared shape that other
agentic primitives (like AuthorityTransitionRecord) can consume.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

NON_CLAIMS: tuple[str, ...] = (
    "EvaluationReport is a diagnostic projection, not a governance decision.",
    "Not execution authorization.",
    "Not investment advice.",
)


class EvaluationSubject(BaseModel):
    """The artifact being evaluated."""

    model_config = ConfigDict(frozen=True)

    subject_type: str
    subject_id: str


class EvaluationFinding(BaseModel):
    """One finding within an EvaluationReport."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["info", "warn", "block"]
    message: str
    recovery_hint: str = ""
    blocked_transitions: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """Common projection of a local evaluator's output.

    Deterministic report_hash enables comparison across runs.
    execution_allowed=False and authority_transition=False are
    hard-coded — this is a diagnostic artifact, not authority.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str = "finharness.evaluation_report.v1"
    report_id: str
    evaluator_id: str
    subject: EvaluationSubject
    status: Literal["pass", "warn", "block"]
    findings: list[EvaluationFinding] = Field(default_factory=list)
    deterministic: bool = True
    report_hash: str = ""
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    authority_transition: bool = False


def _new_id() -> str:
    return f"er_{uuid4().hex[:12]}"


def _compute_hash(report_data: dict) -> str:
    """Deterministic hash of the report content (excluding report_id and hash)."""
    canonical = json.dumps(report_data, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def build_evaluation_report(
    *,
    evaluator_id: str,
    subject_type: str,
    subject_id: str,
    status: Literal["pass", "warn", "block"],
    findings: list[EvaluationFinding] | None = None,
    source_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
) -> EvaluationReport:
    """Build an EvaluationReport with a deterministic hash.

    The hash covers all fields except report_id and report_hash,
    enabling consumers to detect whether the evaluation changed
    between runs.
    """
    report_id = _new_id()
    findings_list = findings or []
    source_refs_list = _dedupe_refs(source_refs or [])
    receipt_refs_list = _dedupe_refs(receipt_refs or [])

    report = EvaluationReport(
        report_id=report_id,
        evaluator_id=evaluator_id,
        subject=EvaluationSubject(
            subject_type=subject_type,
            subject_id=subject_id,
        ),
        status=status,
        findings=findings_list,
        deterministic=True,
        report_hash="",  # set below
        source_refs=source_refs_list,
        receipt_refs=receipt_refs_list,
    )

    # Hash everything except report_id and report_hash itself
    hash_payload = report.model_dump(exclude={"report_id", "report_hash"})
    report_hash = _compute_hash(hash_payload)

    return EvaluationReport(
        report_id=report_id,
        evaluator_id=evaluator_id,
        subject=EvaluationSubject(
            subject_type=subject_type,
            subject_id=subject_id,
        ),
        status=status,
        findings=findings_list,
        deterministic=True,
        report_hash=report_hash,
        source_refs=source_refs_list,
        receipt_refs=receipt_refs_list,
    )


def _dedupe_refs(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


# ── Finding field accessor (dict + dataclass) ───────────────────────────────


def _finding_get(finding: object, key: str, default: Any = "") -> Any:
    """Read a field from a dict or object (dataclass) finding."""
    val = (
        finding.get(key, default)
        if isinstance(finding, dict)
        else getattr(finding, key, default)
    )
    return val if val is not None else default


def _finding_list_get(finding: object, key: str) -> list[str]:
    """Read a list field from a dict or dataclass finding."""
    raw = _finding_get(finding, key, [])
    if isinstance(raw, list):
        return _dedupe_refs(raw)
    return []


# ── Adapter: scaffold candidate preflight → EvaluationReport ────────────────


def evaluation_report_from_scaffold_preflight(
    report: object,
) -> EvaluationReport:
    """Project a ScaffoldCandidatePreflightReport into an EvaluationReport.

    Accepts the real ScaffoldCandidatePreflightReport (status: PreflightStatus,
    findings: list[PreflightFinding] as frozen dataclasses) and dict-based
    test doubles (preflight_status + dict findings) for backward compatibility.
    """
    # status is the canonical field; preflight_status is the test-double fallback
    raw_status = getattr(report, "status", None)
    if raw_status is None:
        raw_status = getattr(report, "preflight_status", "warn")

    proposal_id = getattr(report, "proposal_id", "unknown")
    raw_findings = getattr(report, "findings", []) or []
    raw_receipt_refs = getattr(report, "receipt_refs", []) or []

    status_map: dict[str, Literal["pass", "warn", "block"]] = {
        "pass": "pass",
        "warn": "warn",
        "block": "block",
    }
    status = status_map.get(str(raw_status), "warn")

    findings = [
        EvaluationFinding(
            code=str(_finding_get(f, "code", "preflight_finding")),
            severity=_coerce_severity(_finding_get(f, "severity", "warn")),
            message=str(_finding_get(f, "message", "")),
            recovery_hint=str(_finding_get(f, "recovery_hint", "")),
            source_refs=_finding_list_get(f, "source_refs"),
            receipt_refs=_finding_list_get(f, "receipt_refs"),
        )
        for f in raw_findings
    ]

    return build_evaluation_report(
        evaluator_id="scaffold_candidate_preflight",
        subject_type="scaffold_candidate",
        subject_id=str(proposal_id),
        status=status,
        findings=findings,
        receipt_refs=list(raw_receipt_refs) if isinstance(raw_receipt_refs, list) else [],
    )


# ── Adapter: proposal queue checks → EvaluationReport ──────────────────────


def evaluation_report_from_queue_check(
    queue_check: object,
) -> EvaluationReport:
    """Project proposal queue check output into an EvaluationReport.

    Accepts any object with status, findings (list of dicts with code/
    message/severity), and optional proposal_id and receipt_refs.
    """
    raw_status = getattr(queue_check, "status", "warn")
    proposal_id = getattr(queue_check, "proposal_id", "unknown")
    raw_findings = getattr(queue_check, "findings", []) or []
    raw_receipt_refs = getattr(queue_check, "receipt_refs", []) or []

    status_map: dict[str, Literal["pass", "warn", "block"]] = {
        "pass": "pass",
        "warn": "warn",
        "block": "block",
    }
    status = status_map.get(str(raw_status), "warn")

    findings = [
        EvaluationFinding(
            code=str(f.get("code", "queue_check_finding")),
            severity=_coerce_severity(f.get("severity", "warn")),
            message=str(f.get("message", "")),
            recovery_hint=str(f.get("recovery_hint", "")),
            source_refs=_dedupe_refs(list(f.get("source_refs", []))),
            receipt_refs=_dedupe_refs(list(f.get("receipt_refs", []))),
        )
        for f in raw_findings
        if isinstance(f, dict)
    ]

    return build_evaluation_report(
        evaluator_id="proposal_queue_check",
        subject_type="proposal",
        subject_id=str(proposal_id),
        status=status,
        findings=findings,
        receipt_refs=list(raw_receipt_refs) if isinstance(raw_receipt_refs, list) else [],
    )


def _coerce_severity(raw: object) -> Literal["info", "warn", "block"]:
    valid = {"info", "warn", "block"}
    text = str(raw).strip().lower() if raw is not None else "warn"
    if text in valid:
        return text  # type: ignore[return-value]
    return "warn"
