"""Shared provenance preparation for production capital imports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.artifact_store import (
    ArtifactDescriptor,
    ArtifactNotFoundError,
    ArtifactStore,
)
from finharness.statecore.import_identity import (
    MATERIALIZED_RECORD_IDENTITIES_FIELD,
    MaterializedRecordIdentityError,
    normalize_materialized_record_identities,
)
from finharness.statecore.import_models import (
    IMPORT_COMPLETENESS_STATUSES,
    ImportBatch,
    ImportTombstone,
    ReceiptManifest,
)
from finharness.statecore.receipt_io import atomic_write_bytes, resolve_under

IMPORT_MANIFEST_SCHEMA_VERSION = "finharness.import_manifest.v4"
SOURCE_ARTIFACT_SCHEMA = "finharness.import_source_evidence"
RECEIPT_ARTIFACT_SCHEMA = "finharness.import_receipt"


class ImportProvenanceError(RuntimeError):
    """Raised when import evidence or its immutable binding cannot be trusted."""


@dataclass(frozen=True)
class PreparedImport:
    batch: ImportBatch
    manifest: ReceiptManifest
    receipt_path: Path
    receipt_payload: dict[str, Any]


@dataclass(frozen=True)
class ReceiptProvenance:
    receipt_id: str
    status: str
    batch_id: str | None
    manifest_id: str | None


def receipt_provenance(receipt_id: str, *, engine: Engine) -> ReceiptProvenance:
    """Expose old receipt history without pretending a legacy manifest exists."""
    with Session(engine) as session:
        manifest = session.exec(
            select(ReceiptManifest).where(ReceiptManifest.receipt_id == receipt_id)
        ).one_or_none()
    if manifest is None:
        return ReceiptProvenance(receipt_id, "legacy_unmanifested", None, None)
    return ReceiptProvenance(
        receipt_id,
        manifest.materialization_status,
        manifest.batch_id,
        manifest.manifest_id,
    )


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    ).encode("utf-8")


def _safe_fragment(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-", "."} else "_" for char in value)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def normalize_import_deletions(
    deletions: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, str]]:
    """Return a deterministic, closed deletion-contract representation."""
    normalized: list[dict[str, str]] = []
    for item in deletions or ():
        entry = {
            "record_type": str(item.get("record_type") or "").strip(),
            "record_id": str(item.get("record_id") or "").strip(),
            "reason": str(item.get("reason") or "").strip(),
        }
        if not all(entry.values()):
            raise ImportProvenanceError(
                "import deletion requires record_type, record_id, and reason"
            )
        normalized.append(entry)
    normalized.sort(key=lambda item: (item["record_type"], item["record_id"], item["reason"]))
    if len({tuple(item.values()) for item in normalized}) != len(normalized):
        raise ImportProvenanceError("import deletion plan contains duplicate entries")
    return normalized


def derive_import_tombstone_id(
    batch_id: str,
    record_type: str,
    record_id: str,
) -> str:
    """Return the canonical identity for one receipt-bound deletion fact."""
    return _stable_id("import_tombstone", batch_id, record_type, record_id)


def build_import_tombstone(
    *,
    batch: ImportBatch,
    record_type: str,
    record_id: str,
    reason: str,
) -> ImportTombstone:
    """Construct the exact database mirror of one immutable deletion spec."""
    normalized = normalize_import_deletions(
        (
            {
                "record_type": record_type,
                "record_id": record_id,
                "reason": reason,
            },
        )
    )[0]
    return ImportTombstone(
        tombstone_id=derive_import_tombstone_id(
            batch.batch_id,
            normalized["record_type"],
            normalized["record_id"],
        ),
        batch_id=batch.batch_id,
        source_kind=batch.source_kind,
        record_type=normalized["record_type"],
        record_id=normalized["record_id"],
        reason=normalized["reason"],
        source_refs=[batch.source_artifact_id],
        as_of_utc=batch.as_of_utc,
        authority_level="read_only",
    )


_IMPORT_IDENTITY_TIME_FIELDS = (
    "effective_at_utc",
    "observed_at_utc",
    "valued_at_utc",
)


def canonical_import_contract_payload(
    *,
    coverage_mode: str,
    covered_domains: Sequence[str] | None = None,
    deletions: Sequence[Mapping[str, Any]] | None = None,
    identity_time_semantics: Mapping[str, Any] | None = None,
    supersedes_batch_id: str | None = None,
    correction_reason: str | None = None,
    corporate_action_status: str | None = None,
) -> dict[str, Any]:
    """Build the deterministic import-intent contract used by identity hashes."""
    payload: dict[str, Any] = {
        "coverage_mode": coverage_mode,
        "covered_domains": sorted(set(covered_domains or ())),
        "explicit_deletions": normalize_import_deletions(deletions),
        "time_semantics": (
            {
                field: identity_time_semantics.get(field)
                for field in _IMPORT_IDENTITY_TIME_FIELDS
            }
            if identity_time_semantics is not None
            else {}
        ),
        "supersedes_batch_id": supersedes_batch_id,
        "correction_reason": correction_reason,
    }
    if corporate_action_status is not None:
        payload["corporate_action_status"] = corporate_action_status
    return payload


def _contract_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def derive_import_contract_digest(
    *,
    coverage_mode: str,
    covered_domains: Sequence[str] | None = None,
    deletions: Sequence[Mapping[str, Any]] | None = None,
    identity_time_semantics: Mapping[str, Any] | None = None,
    supersedes_batch_id: str | None = None,
    correction_reason: str | None = None,
    corporate_action_status: str,
) -> str:
    payload = canonical_import_contract_payload(
        coverage_mode=coverage_mode,
        covered_domains=covered_domains,
        deletions=deletions,
        identity_time_semantics=identity_time_semantics,
        supersedes_batch_id=supersedes_batch_id,
        correction_reason=correction_reason,
        corporate_action_status=corporate_action_status,
    )
    return hashlib.sha256(_contract_bytes(payload)).hexdigest()[:32]


def derive_import_batch_id(
    *,
    source_kind: str,
    source_id: str,
    source_sha256: str,
    adapter_version: str,
    coverage_mode: str,
    covered_domains: Sequence[str] | None = None,
    deletions: Sequence[Mapping[str, Any]] | None = None,
    identity_time_semantics: Mapping[str, Any] | None = None,
    supersedes_batch_id: str | None = None,
    correction_reason: str | None = None,
) -> str:
    """Derive one deterministic batch identity from source and import intent."""
    contract = canonical_import_contract_payload(
        coverage_mode=coverage_mode,
        covered_domains=covered_domains,
        deletions=deletions,
        identity_time_semantics=identity_time_semantics,
        supersedes_batch_id=supersedes_batch_id,
        correction_reason=correction_reason,
    )
    return _stable_id(
        "import_batch",
        source_kind,
        source_id,
        source_sha256,
        adapter_version,
        IMPORT_MANIFEST_SCHEMA_VERSION,
        _contract_bytes(contract).decode("utf-8"),
    )


def _put_or_verify(
    store: ArtifactStore,
    *,
    artifact_id: str,
    content: bytes,
    artifact_schema: str,
    created_at_utc: str,
    source_refs: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> ArtifactDescriptor:
    try:
        existing = store.descriptor(artifact_id)
    except ArtifactNotFoundError:
        return store.put(
            artifact_id=artifact_id,
            content=content,
            artifact_schema=artifact_schema,
            artifact_schema_version=IMPORT_MANIFEST_SCHEMA_VERSION,
            media_type=(
                "application/json"
                if content.startswith((b"{", b"["))
                else "application/octet-stream"
            ),
            owner_domain="capital_imports",
            created_at_utc=created_at_utc,
            source_refs=source_refs,
            metadata=metadata or {},
        )
    if store.read(artifact_id) != content:
        raise ImportProvenanceError(f"immutable import artifact conflict: {artifact_id}")
    if existing.artifact_schema != artifact_schema or existing.owner_domain != "capital_imports":
        raise ImportProvenanceError(f"import artifact descriptor mismatch: {artifact_id}")
    return existing


def persist_source_evidence(
    *,
    source_kind: str,
    source_content: bytes,
    source_sha256: str,
    artifact_store: ArtifactStore,
    created_at_utc: str,
) -> ArtifactDescriptor:
    """Persist or recover the stable clock for content-addressed source evidence."""
    if hashlib.sha256(source_content).hexdigest() != source_sha256:
        raise ImportProvenanceError("source evidence bytes do not match source_sha256")
    artifact_id = f"import_source_{_safe_fragment(source_kind)}_{source_sha256[:24]}"
    return _put_or_verify(
        artifact_store,
        artifact_id=artifact_id,
        content=source_content,
        artifact_schema=SOURCE_ARTIFACT_SCHEMA,
        created_at_utc=created_at_utc,
        metadata={"source_kind": source_kind, "source_sha256": source_sha256},
    )



def _normalize_materialization_proof(
    identities: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    try:
        return normalize_materialized_record_identities(identities)
    except MaterializedRecordIdentityError as exc:
        raise ImportProvenanceError(str(exc)) from exc

def prepare_import(
    *,
    source_kind: str,
    source_id: str,
    source_content: bytes,
    source_sha256: str,
    adapter_version: str,
    coverage_mode: str,
    record_counts: dict[str, int],
    snapshot_id: str,
    receipt_id: str,
    receipt_root: str | Path,
    receipt_ref: str,
    artifact_store: ArtifactStore,
    receipt_payload: dict[str, Any],
    created_at_utc: str,
    completeness_status: str,
    time_semantics: dict[str, Any],
    findings: list[dict[str, Any]],
    materialized_record_identities: Sequence[Mapping[str, Any]] = (),
    covered_domains: list[str] | None = None,
    identity_time_semantics: Mapping[str, Any] | None = None,
    supersedes_batch_id: str | None = None,
    correction_reason: str | None = None,
    corporate_action_status: str = "unsupported_gap",
    corporate_action_gaps: list[str] | None = None,
) -> PreparedImport:
    """Persist immutable evidence and construct the DB transaction envelope."""
    if coverage_mode not in {"full", "delta"}:
        raise ImportProvenanceError("coverage_mode must be full or delta")
    if completeness_status not in IMPORT_COMPLETENESS_STATUSES:
        raise ImportProvenanceError("completeness_status is outside the closed set")
    required_clocks = {
        "effective_at_utc",
        "observed_at_utc",
        "valued_at_utc",
        "ingested_at_utc",
        "recorded_at_utc",
    }
    if set(time_semantics) != required_clocks:
        raise ImportProvenanceError("time_semantics must contain the five canonical clocks")
    if any(finding.get("severity") not in {"partial", "blocking"} for finding in findings):
        raise ImportProvenanceError("import finding severity is outside the closed set")
    if (supersedes_batch_id is None) != (correction_reason is None):
        raise ImportProvenanceError(
            "supersedes_batch_id and correction_reason must be supplied together"
        )
    if correction_reason is not None and not correction_reason.strip():
        raise ImportProvenanceError("correction_reason must be non-empty")
    if corporate_action_status not in {"not_applicable", "unsupported_gap"}:
        raise ImportProvenanceError("corporate_action_status is outside the closed set")
    resolved_domains = sorted(set(covered_domains or record_counts))
    resolved_materialized_identities = _normalize_materialization_proof(
        materialized_record_identities
    )
    raw_deletion_plan = receipt_payload.get("deletion_plan")
    if raw_deletion_plan is not None and not isinstance(raw_deletion_plan, dict):
        raise ImportProvenanceError("deletion_plan must be an object")
    explicit_deletions = normalize_import_deletions(
        raw_deletion_plan.get("explicit", []) if raw_deletion_plan else []
    )
    automatic_deletions = normalize_import_deletions(
        raw_deletion_plan.get("automatic", []) if raw_deletion_plan else []
    )
    if raw_deletion_plan is not None:
        planned_domains = sorted(set(raw_deletion_plan.get("covered_domains", [])))
        if planned_domains != resolved_domains:
            raise ImportProvenanceError(
                "deletion_plan covered_domains do not match import coverage"
            )
        receipt_payload = {
            **receipt_payload,
            "deletions": explicit_deletions,
            "deletion_plan": {
                "explicit": explicit_deletions,
                "automatic": automatic_deletions,
                "domain": str(raw_deletion_plan.get("domain") or "").strip(),
                "covered_domains": resolved_domains,
            },
        }
    resolved_corporate_action_gaps = sorted(set(corporate_action_gaps or []))
    if corporate_action_status == "unsupported_gap" and not resolved_corporate_action_gaps:
        resolved_corporate_action_gaps = ["corporate_action_semantics_not_supported"]
    batch_id = derive_import_batch_id(
        source_kind=source_kind,
        source_id=source_id,
        source_sha256=source_sha256,
        adapter_version=adapter_version,
        coverage_mode=coverage_mode,
        covered_domains=resolved_domains,
        deletions=explicit_deletions,
        identity_time_semantics=identity_time_semantics,
        supersedes_batch_id=supersedes_batch_id,
        correction_reason=correction_reason,
    )
    source_descriptor = persist_source_evidence(
        source_kind=source_kind,
        source_content=source_content,
        source_sha256=source_sha256,
        artifact_store=artifact_store,
        created_at_utc=created_at_utc,
    )
    source_artifact_id = source_descriptor.artifact_id
    stable_created_at = source_descriptor.created_at_utc
    manifest_id = _stable_id("receipt_manifest", batch_id, receipt_id)
    complete_receipt = {
        **receipt_payload,
        "import_batch_id": batch_id,
        "receipt_manifest_id": manifest_id,
        "source_artifact_id": source_artifact_id,
        "coverage_mode": coverage_mode,
        "import_schema_version": IMPORT_MANIFEST_SCHEMA_VERSION,
        "completeness_status": completeness_status,
        "time_semantics": time_semantics,
        "findings": findings,
        "covered_domains": resolved_domains,
        MATERIALIZED_RECORD_IDENTITIES_FIELD: resolved_materialized_identities,
        "supersedes_batch_id": supersedes_batch_id,
        "correction_reason": correction_reason,
        "corporate_action_status": corporate_action_status,
        "corporate_action_gaps": resolved_corporate_action_gaps,
        "created_at_utc": stable_created_at,
    }
    receipt_bytes = canonical_json_bytes(complete_receipt)
    receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
    receipt_artifact_id = f"import_receipt_{receipt_sha256[:24]}"
    _put_or_verify(
        artifact_store,
        artifact_id=receipt_artifact_id,
        content=receipt_bytes,
        artifact_schema=RECEIPT_ARTIFACT_SCHEMA,
        created_at_utc=stable_created_at,
        source_refs=(source_artifact_id,),
        metadata={"batch_id": batch_id, "receipt_id": receipt_id},
    )
    receipt_path = resolve_under(receipt_root, f"{receipt_id}.json")
    atomic_write_bytes(receipt_path, receipt_bytes)
    contract_digest = derive_import_contract_digest(
        coverage_mode=coverage_mode,
        covered_domains=resolved_domains,
        deletions=explicit_deletions,
        identity_time_semantics=identity_time_semantics,
        supersedes_batch_id=supersedes_batch_id,
        correction_reason=correction_reason,
        corporate_action_status=corporate_action_status,
    )

    batch = ImportBatch(
        batch_id=batch_id,
        source_kind=source_kind,
        source_id=source_id,
        coverage_mode=coverage_mode,
        source_sha256=source_sha256,
        source_artifact_id=source_artifact_id,
        adapter_version=adapter_version,
        import_schema_version=IMPORT_MANIFEST_SCHEMA_VERSION,
        contract_digest=contract_digest,
        record_counts=record_counts,
        covered_domains=resolved_domains,
        supersedes_batch_id=supersedes_batch_id,
        correction_reason=correction_reason,
        corporate_action_status=corporate_action_status,
        corporate_action_gaps=resolved_corporate_action_gaps,
        completeness_status=completeness_status,
        time_semantics=time_semantics,
        findings=findings,
        as_of_utc=stable_created_at,
        authority_level="read_only",
    )
    manifest = ReceiptManifest(
        manifest_id=manifest_id,
        batch_id=batch_id,
        receipt_id=receipt_id,
        receipt_ref=receipt_ref,
        receipt_sha256=receipt_sha256,
        receipt_artifact_id=receipt_artifact_id,
        source_artifact_id=source_artifact_id,
        snapshot_id=snapshot_id,
        materialization_status="materialized",
        record_counts=record_counts,
        materialized_at_utc=stable_created_at,
        as_of_utc=stable_created_at,
        authority_level="read_only",
    )
    return PreparedImport(batch, manifest, receipt_path, complete_receipt)
