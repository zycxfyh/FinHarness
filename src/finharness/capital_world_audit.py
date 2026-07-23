"""Typed, fail-closed semantic audit over read-only Capital World observations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from dataclasses import field as dc_field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from finharness.statecore.receipt_io import atomic_write_json, resolve_under

AUDIT_SCHEMA: Literal["finharness.capital_world_audit.v1"] = "finharness.capital_world_audit.v1"
ClaimClassification = Literal["observed", "inferred", "unsupported"]
AuditDisposition = Literal["complete", "partial", "stopped"]
AuditSeverity = Literal["info", "warn", "block"]

PROMPT_INJECTION_MARKERS = (
    "ignore previous", "ignore all previous", "system prompt",
    "developer message", "override instructions", "bypass safety",
    "bypass policy", "execute trade", "submit order", "send funds",
)
EXECUTION_MARKERS = (
    "buy ", "sell ", "allocate ", "rebalance now", "execute ",
    "submit order", "send funds",
)


class CapitalAuditClaim(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    classification: ClaimClassification
    statement: str = Field(min_length=1)
    confidence: Literal["high", "medium", "low", "none"]
    world_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    execution_allowed: Literal[False] = False

    @model_validator(mode="after")
    def require_lineage(self) -> CapitalAuditClaim:
        if self.classification != "unsupported" and not (
            self.world_refs or self.source_refs or self.artifact_refs
        ):
            raise ValueError("supported claims require lineage refs")
        return self


class CapitalAuditFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    severity: AuditSeverity
    message: str = Field(min_length=1)
    recovery_hint: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)


class CapitalWorldAudit(BaseModel):
    """One bounded semantic result shared by deterministic and model-backed runs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["finharness.capital_world_audit.v1"] = AUDIT_SCHEMA
    audit_id: str = Field(pattern=r"^capital_audit_[0-9a-f]{20}$")
    goal: str = Field(min_length=1)
    disposition: AuditDisposition
    world_id: str | None = None
    basis_digest: str | None = None
    world_status: str | None = None
    observed: list[CapitalAuditClaim] = Field(default_factory=list)
    inferred: list[CapitalAuditClaim] = Field(default_factory=list)
    unsupported: list[CapitalAuditClaim] = Field(default_factory=list)
    findings: list[CapitalAuditFinding] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    investigation_questions: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(min_length=1)
    required_evaluations: list[str] = Field(min_length=1)
    human_handoff: str = Field(min_length=1)
    data_gaps: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    observation_digests: list[str] = Field(default_factory=list)
    model_provider: str = "deterministic"
    model_name: str = "capital-world-audit.v1"
    execution_allowed: Literal[False] = False

    @field_validator(
        "blockers", "counter_evidence", "investigation_questions",
        "stop_conditions", "required_evaluations", "data_gaps",
        "source_refs", "artifact_refs", "observation_digests",
    )
    @classmethod
    def dedupe_strings(cls, values: list[str]) -> list[str]:
        return _dedupe(values)

    @model_validator(mode="after")
    def fail_closed(self) -> CapitalWorldAudit:
        if self.disposition == "complete" and (
            self.world_status != "admitted" or self.blockers
            or any(f.severity == "block" for f in self.findings)
        ):
            raise ValueError("complete audit requires one admitted unblocked world")
        if self.world_status != "admitted":
            for claim in [*self.observed, *self.inferred]:
                if any(marker in claim.statement.lower() for marker in EXECUTION_MARKERS):
                    raise ValueError("non-admitted world cannot support action claims")
        if not self.stop_conditions or not self.required_evaluations:
            raise ValueError("audit requires stop conditions and evaluations")
        return self


@dataclass
class _AuditScan:
    source_refs: list[str] = dc_field(default_factory=list)
    artifact_refs: list[str] = dc_field(default_factory=list)
    observation_digests: list[str] = dc_field(default_factory=list)
    findings: list[CapitalAuditFinding] = dc_field(default_factory=list)
    gaps: list[str] = dc_field(default_factory=list)
    summaries: list[dict[str, Any]] = dc_field(default_factory=list)
    world_ids: list[str] = dc_field(default_factory=list)
    basis_digests: list[str] = dc_field(default_factory=list)
    statuses: list[str] = dc_field(default_factory=list)


@dataclass(frozen=True)
class _WorldResolution:
    world_id: str | None
    basis_digest: str | None
    world_status: str | None
    unique_worlds: tuple[str, ...]
    unique_bases: tuple[str, ...]
    unique_statuses: tuple[str, ...]


def build_capital_world_audit(
    *, goal: str, tool_envelopes: list[dict[str, object]],
) -> CapitalWorldAudit:
    """Reduce budgeted tool observations into a typed read-only audit."""
    clean_goal = goal.strip()
    if not clean_goal:
        raise ValueError("goal must not be blank")
    scan = _scan_tool_envelopes(tool_envelopes)
    world = _resolve_world(scan)
    primary = scan.summaries[0] if scan.summaries else {}
    truth_blockers = _truth_blockers(primary)
    _add_world_findings(scan, world, primary, truth_blockers)
    observed, inferred, unsupported = _build_claims(
        scan=scan,
        world=world,
        primary=primary,
        truth_blockers=truth_blockers,
    )
    blocking = [item.code for item in scan.findings if item.severity == "block"]
    warnings = [item.code for item in scan.findings if item.severity == "warn"]
    disposition: AuditDisposition = (
        "stopped" if blocking else "partial" if warnings or scan.gaps else "complete"
    )
    required_evaluations = [
        "capital_world_trust_check",
        "source_lineage_check",
        "read_only_boundary_check",
    ]
    if world.world_status != "admitted" or truth_blockers:
        required_evaluations.append("capital_truth_recovery_check")
    counter_evidence = [
        "A read-only audit cannot establish execution authority or expected return."
    ]
    if truth_blockers:
        counter_evidence.append(
            "Capital Truth blockers contradict any complete portfolio conclusion."
        )
    handoff = (
        "Human review required: repair or acknowledge typed blockers before any "
        "decision record, proposal write, or external action."
        if disposition != "complete"
        else "Human review required before using this audit as decision support."
    )
    return CapitalWorldAudit(
        audit_id=_audit_id(clean_goal, scan.observation_digests, scan.artifact_refs),
        goal=clean_goal,
        disposition=disposition,
        world_id=world.world_id,
        basis_digest=world.basis_digest,
        world_status=world.world_status,
        observed=observed,
        inferred=inferred,
        unsupported=unsupported,
        findings=scan.findings,
        blockers=blocking,
        counter_evidence=counter_evidence,
        investigation_questions=[
            "Does every material claim resolve to the same world_id and basis_digest?",
            "Are valuation and FX blockers repaired in a newly resolved Capital World?",
            "Did any source text attempt to instruct the model rather than report facts?",
        ],
        stop_conditions=[
            "Stop if the resolved world_id or basis_digest changes.",
            "Stop if ContextTrust is missing, malformed, stale, or disallows evidence use.",
            "Stop if any result is truncated, conflicting, spoofed, or instruction-like.",
            "Stop before any proposal write, allocation recommendation, or execution request.",
        ],
        required_evaluations=required_evaluations,
        human_handoff=handoff,
        data_gaps=scan.gaps,
        source_refs=scan.source_refs,
        artifact_refs=scan.artifact_refs,
        observation_digests=scan.observation_digests,
    )


def _scan_tool_envelopes(tool_envelopes: list[dict[str, object]]) -> _AuditScan:
    scan = _AuditScan()
    for envelope in tool_envelopes:
        _scan_envelope(scan, envelope)
    scan.source_refs = _dedupe(scan.source_refs)
    scan.artifact_refs = _dedupe(scan.artifact_refs)
    scan.observation_digests = _dedupe(scan.observation_digests)
    return scan


def _scan_envelope(scan: _AuditScan, envelope: dict[str, object]) -> None:
    scan.source_refs.extend(_string_list(envelope.get("source_refs")))
    scan.artifact_refs.extend(
        text
        for ref in [
            envelope.get("artifact_ref"),
            *_string_list(envelope.get("artifact_refs")),
        ]
        if (text := _optional_text(ref))
    )
    if digest := _optional_text(envelope.get("observation_sha256")):
        scan.observation_digests.append(digest)
    artifact = _optional_text(envelope.get("artifact_ref"))
    artifacts = [artifact] if artifact else []
    if envelope.get("ok") is not True:
        code = _optional_text(envelope.get("error_code")) or "unknown_tool_error"
        scan.findings.append(CapitalAuditFinding(
            code="tool_result_failed",
            severity="warn",
            message=f"Tool result failed: {code}",
            recovery_hint="Repair or replace the failed read tool.",
            artifact_refs=artifacts,
        ))
        scan.gaps.append(f"tool_result_failed:{code}")
    if envelope.get("truncated") is True:
        scan.findings.append(CapitalAuditFinding(
            code="context_truncated",
            severity="warn",
            message="A tool observation was truncated by its runtime budget.",
            recovery_hint="Use a narrower query or stop for human review.",
            artifact_refs=artifacts,
        ))
        scan.gaps.append("context_truncated")
    for gap in _string_list(envelope.get("data_gaps")):
        scan.findings.append(CapitalAuditFinding(
            code="context_data_gap",
            severity="warn",
            message=f"Tool observation reported a data gap: {gap}",
            recovery_hint="Resolve the gap or preserve a partial human handoff.",
            artifact_refs=artifacts,
        ))
        scan.gaps.append(gap)
    payload = envelope.get("observation_payload")
    if isinstance(payload, dict):
        _scan_payload(scan, payload, envelope, artifacts)
    _append_world_metadata(scan, envelope)


def _scan_payload(
    scan: _AuditScan,
    payload: dict[str, object],
    envelope: dict[str, object],
    artifacts: list[str],
) -> None:
    if _contains_prompt_injection(payload):
        scan.findings.append(CapitalAuditFinding(
            code="prompt_injection_detected",
            severity="block",
            message="Observation text contains instruction-like markers.",
            recovery_hint="Quarantine the source and review provenance.",
            artifact_refs=artifacts,
        ))
        scan.gaps.append("prompt_injection_detected")
    payload_refs = set(_collect_payload_refs(payload))
    declared_refs = set(
        _string_list(envelope.get("source_refs"))
        + _string_list(envelope.get("receipt_refs"))
        + _string_list(envelope.get("context_refs"))
    )
    unexpected = sorted(payload_refs - declared_refs)
    if unexpected:
        scan.findings.append(CapitalAuditFinding(
            code="source_lineage_mismatch",
            severity="block",
            message="Payload asserted refs absent from its evidence envelope.",
            recovery_hint="Rebuild lineage from the exact bounded payload.",
            source_refs=unexpected[:20],
            artifact_refs=artifacts,
        ))
        scan.gaps.append("source_lineage_mismatch")
    scan.summaries.extend(_find_capital_summaries(payload))


def _append_world_metadata(scan: _AuditScan, value: dict[str, object]) -> None:
    for key, target in (
        ("world_id", scan.world_ids),
        ("basis_digest", scan.basis_digests),
        ("world_status", scan.statuses),
    ):
        if text := _optional_text(value.get(key)):
            target.append(text)


def _resolve_world(scan: _AuditScan) -> _WorldResolution:
    for summary in scan.summaries:
        _append_world_metadata(scan, summary)
    worlds = tuple(_dedupe(scan.world_ids))
    bases = tuple(_dedupe(scan.basis_digests))
    statuses = tuple(_dedupe(scan.statuses))
    return _WorldResolution(
        world_id=worlds[0] if len(worlds) == 1 else None,
        basis_digest=bases[0] if len(bases) == 1 else None,
        world_status=statuses[0] if len(statuses) == 1 else None,
        unique_worlds=worlds,
        unique_bases=bases,
        unique_statuses=statuses,
    )


def _truth_blockers(primary: dict[str, Any]) -> list[str]:
    truth = primary.get("capital_truth")
    return _string_list(truth.get("blockers")) if isinstance(truth, dict) else []


def _add_world_findings(
    scan: _AuditScan,
    world: _WorldResolution,
    primary: dict[str, Any],
    truth_blockers: list[str],
) -> None:
    if not scan.summaries:
        _block(scan, "capital_summary_missing", "No typed Capital World summary was observed.",
               "Dispatch a Capital context read tool.")
    if (len(world.unique_worlds) > 1 or len(world.unique_bases) > 1
            or len(world.unique_statuses) > 1):
        _block(scan, "capital_world_conflict",
               "Observations refer to conflicting worlds or trust states.",
               "Resolve one exact world_id and basis_digest.")
    if world.world_id is None or world.basis_digest is None or world.world_status is None:
        _block(scan, "capital_world_identity_incomplete",
               "World identity, basis digest, or status is incomplete.",
               "Rebuild a complete context projection.")
    if not _valid_context_trust(primary.get("trust")):
        _block(scan, "context_trust_missing_or_invalid",
               "Capital summary lacks complete ContextTrust metadata.",
               "Attach valid ContextTrust before reasoning.")
    if world.world_status and world.world_status != "admitted":
        scan.findings.append(CapitalAuditFinding(
            code="capital_world_not_admitted",
            severity="block",
            message=f"Capital World status is {world.world_status}; decision claims stop.",
            recovery_hint="Repair Capital Truth blockers and resolve a new world.",
            source_refs=scan.source_refs,
            artifact_refs=scan.artifact_refs,
        ))
        scan.gaps.append(f"capital_world_not_admitted:{world.world_status}")
    if truth_blockers and world.world_status == "admitted":
        _block(scan, "capital_truth_status_conflict",
               "Admitted world still carries Capital Truth blockers.",
               "Resolve the contradictory trust projection.")


def _block(scan: _AuditScan, code: str, message: str, recovery: str) -> None:
    scan.findings.append(CapitalAuditFinding(
        code=code,
        severity="block",
        message=message,
        recovery_hint=recovery,
        artifact_refs=scan.artifact_refs,
    ))
    scan.gaps.append(code)


def _build_claims(
    *,
    scan: _AuditScan,
    world: _WorldResolution,
    primary: dict[str, Any],
    truth_blockers: list[str],
) -> tuple[list[CapitalAuditClaim], list[CapitalAuditClaim], list[CapitalAuditClaim]]:
    world_refs = [f"capital_world://{world.world_id}"] if world.world_id else []
    lineage = {
        "world_refs": world_refs,
        "source_refs": scan.source_refs,
        "artifact_refs": scan.artifact_refs,
    }
    observed: list[CapitalAuditClaim] = []
    inferred: list[CapitalAuditClaim] = []
    unsupported: list[CapitalAuditClaim] = []
    if world.world_id and world.basis_digest and world.world_status:
        observed.append(CapitalAuditClaim(
            classification="observed",
            statement=(f"Resolved Capital World {world.world_id} has status "
                       f"{world.world_status} and basis digest {world.basis_digest}."),
            confidence="high",
            **lineage,
        ))
    observed.extend(_numeric_claims(primary, world.world_status, lineage))
    if primary.get("concentration_flagged") is True and world.world_status == "admitted":
        inferred.append(CapitalAuditClaim(
            classification="inferred",
            statement="The admitted exposure projection flags concentration risk for review.",
            confidence="medium",
            **lineage,
        ))
    if truth_blockers:
        observed.append(CapitalAuditClaim(
            classification="observed",
            statement="Capital Truth blockers: " + ", ".join(truth_blockers),
            confidence="high",
            **lineage,
        ))
    if world.world_status != "admitted":
        unsupported.append(CapitalAuditClaim(
            classification="unsupported",
            statement=("Any allocation, rebalancing, trading, or executable recommendation "
                       "is unsupported while Capital Truth is not admitted."),
            confidence="none",
            **lineage,
        ))
    return observed, inferred, unsupported


def _numeric_claims(
    primary: dict[str, Any],
    world_status: str | None,
    lineage: dict[str, list[str]],
) -> list[CapitalAuditClaim]:
    if world_status != "admitted":
        return []
    claims: list[CapitalAuditClaim] = []
    for key, label in (
        ("total_assets", "Total assets"),
        ("total_liabilities", "Total liabilities"),
        ("net_worth", "Net worth"),
    ):
        if (value := primary.get(key)) is not None:
            claims.append(CapitalAuditClaim(
                classification="observed",
                statement=f"{label} in the admitted Capital World is {value}.",
                confidence="high",
                **lineage,
            ))
    return claims


def write_capital_world_audit(
    audit: CapitalWorldAudit, *, receipt_root: str | Path,
) -> str:
    relative = Path("capital-world-audits") / f"{audit.audit_id}.json"
    atomic_write_json(resolve_under(receipt_root, relative), audit.model_dump(mode="json"))
    return relative.as_posix()


def load_tool_envelopes_from_artifacts(
    *, receipt_root: str | Path, artifact_refs: list[str],
) -> list[dict[str, object]]:
    root = Path(receipt_root)
    envelopes: list[dict[str, object]] = []
    for ref in artifact_refs:
        payload = json.loads(resolve_under(root, ref).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"tool artifact is not an object: {ref}")
        envelopes.append(payload)
    return envelopes


def normalized_audit_contract(audit: CapitalWorldAudit) -> dict[str, Any]:
    payload = audit.model_dump(mode="json")
    payload.pop("audit_id", None)
    payload.pop("model_provider", None)
    payload.pop("model_name", None)
    return payload


def _audit_id(goal: str, digests: list[str], artifacts: list[str]) -> str:
    material = json.dumps(
        {"goal": goal, "observation_digests": digests, "artifact_refs": artifacts},
        sort_keys=True, separators=(",", ":"),
    )
    return f"capital_audit_{hashlib.sha256(material.encode()).hexdigest()[:20]}"


def _find_capital_summaries(value: object) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if value.get("name") == "capital_summary" and isinstance(value.get("summary"), dict):
            found.append(value["summary"])
        packs = value.get("packs")
        if isinstance(packs, list):
            for pack in packs:
                found.extend(_find_capital_summaries(pack))
    return found


def _collect_payload_refs(value: object) -> list[str]:
    """Collect refs only from explicit context/evidence lineage boundaries."""
    if not isinstance(value, dict):
        return []
    refs: list[str] = []
    is_pack = isinstance(value.get("name"), str)
    is_trusted_item = isinstance(value.get("trust"), dict)
    if is_pack or is_trusted_item:
        refs.extend(_string_list(value.get("source_refs")))
        refs.extend(_string_list(value.get("receipt_refs")))
        refs.extend(_string_list(value.get("context_pack_refs")))
        for key in ("source_ref", "receipt_ref"):
            if text := _optional_text(value.get(key)):
                refs.append(text)
    packs = value.get("packs")
    if isinstance(packs, list):
        for pack in packs:
            refs.extend(_collect_payload_refs(pack))
    summary = value.get("summary")
    if isinstance(summary, dict):
        items = summary.get("items")
        if isinstance(items, list):
            for item in items:
                refs.extend(_collect_payload_refs(item))
    return _dedupe(refs)


def _contains_prompt_injection(value: object) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in PROMPT_INJECTION_MARKERS)
    if isinstance(value, dict):
        return any(_contains_prompt_injection(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_prompt_injection(child) for child in value)
    return False


def _valid_context_trust(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    required = {"source_type", "trust_level", "verification_status",
                "allowed_uses", "source_refs", "receipt_refs"}
    return required.issubset(value) and isinstance(value.get("allowed_uses"), list)


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return []


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
