# ruff: noqa: C901
"""Cross-store audit and fail-closed recovery for production capital imports."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, delete
from sqlmodel import Session, col, select

from finharness.artifact_store import (
    ArtifactDescriptor,
    ArtifactRecoveryPort,
    ArtifactStore,
    ArtifactStoreError,
    LocalArtifactStore,
)
from finharness.capital_import_registry import (
    PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES,
    materialized_source_for,
)
from finharness.import_provenance import RECEIPT_ARTIFACT_SCHEMA, canonical_json_bytes
from finharness.project_paths import ROOT
from finharness.statecore.models import (
    ImportBatch,
    ReceiptIndex,
    ReceiptManifest,
    Snapshot,
)
from finharness.statecore.receipt_io import atomic_write_bytes, atomic_write_json, resolve_under

CAPITAL_IMPORT_AUDIT_SCHEMA = "finharness.capital_import_audit.v1"
CAPITAL_IMPORT_RECOVERY_SCHEMA = "finharness.capital_import_recovery.v1"
CAPITAL_IMPORT_RECOVERY_ARTIFACT_SCHEMA = "finharness.capital_import_recovery_receipt"
PRODUCTION_IMPORT_KINDS = set(PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES)


class CapitalImportRecoveryError(RuntimeError):
    """Raised when a requested repair cannot be applied without guessing."""


class CapitalImportFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    batch_id: str | None = None
    receipt_id: str | None = None
    artifact_id: str | None = None
    path: str | None = None
    message: str
    recoverable: bool
    recovery_action: str
    blocks_verified_state: bool = True


class CapitalImportAuditReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_schema: str = Field(
        default=CAPITAL_IMPORT_AUDIT_SCHEMA,
        validation_alias="schema",
        serialization_alias="schema",
    )
    created_at_utc: str
    ok: bool
    batch_count: int
    manifest_count: int
    receipt_artifact_count: int
    verified_batch_ids: tuple[str, ...]
    findings: tuple[CapitalImportFinding, ...]


class CapitalImportRecoveryReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    receipt_schema: str = Field(
        default=CAPITAL_IMPORT_RECOVERY_SCHEMA,
        validation_alias="schema",
        serialization_alias="schema",
    )
    recovery_id: str
    created_at_utc: str
    dry_run: bool
    before: CapitalImportAuditReport
    after: CapitalImportAuditReport
    actions: tuple[str, ...]
    unresolved_findings: tuple[CapitalImportFinding, ...]
    execution_allowed: bool = False


def _read_path(ref: str) -> Path:
    path = Path(ref)
    return path if path.is_absolute() else ROOT / path


def _finding(
    code: str,
    *,
    batch_id: str | None = None,
    receipt_id: str | None = None,
    artifact_id: str | None = None,
    path: str | None = None,
    recoverable: bool,
    recovery_action: str,
    message: str | None = None,
) -> CapitalImportFinding:
    return CapitalImportFinding(
        code=code,
        batch_id=batch_id,
        receipt_id=receipt_id,
        artifact_id=artifact_id,
        path=path,
        message=message or code.replace("_", " "),
        recoverable=recoverable,
        recovery_action=recovery_action,
    )


def _receipt_payload(store: ArtifactStore, descriptor: ArtifactDescriptor) -> dict[str, Any]:
    try:
        payload = json.loads(store.read(descriptor.artifact_id))
    except (ArtifactStoreError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CapitalImportRecoveryError(
            f"receipt artifact is unreadable: {descriptor.artifact_id}"
        ) from exc
    if not isinstance(payload, dict):
        raise CapitalImportRecoveryError(
            f"receipt artifact is not an object: {descriptor.artifact_id}"
        )
    return payload


def _audit_manifest_evidence(
    manifest: ReceiptManifest,
    batch: ImportBatch,
    descriptor: ArtifactDescriptor | None,
    store: ArtifactStore,
) -> list[CapitalImportFinding]:
    findings: list[CapitalImportFinding] = []
    if descriptor is None:
        findings.append(
            _finding(
                "manifest_receipt_artifact_missing",
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                artifact_id=manifest.receipt_artifact_id,
                recoverable=False,
                recovery_action="restore_receipt_artifact",
            )
        )
    else:
        try:
            content = store.read(descriptor.artifact_id)
            payload = json.loads(content)
        except (ArtifactStoreError, UnicodeDecodeError, json.JSONDecodeError):
            content = b""
            payload = {}
        if hashlib.sha256(content).hexdigest() != manifest.receipt_sha256:
            findings.append(
                _finding(
                    "manifest_receipt_artifact_hash_mismatch",
                    batch_id=batch.batch_id,
                    receipt_id=manifest.receipt_id,
                    artifact_id=descriptor.artifact_id,
                    recoverable=False,
                    recovery_action="restore_receipt_artifact",
                )
            )
        elif any(
            payload.get(key) != value
            for key, value in {
                "import_batch_id": batch.batch_id,
                "receipt_manifest_id": manifest.manifest_id,
                "source_artifact_id": batch.source_artifact_id,
                "receipt_id": manifest.receipt_id,
            }.items()
        ):
            findings.append(
                _finding(
                    "receipt_binding_mismatch",
                    batch_id=batch.batch_id,
                    receipt_id=manifest.receipt_id,
                    artifact_id=descriptor.artifact_id,
                    recoverable=False,
                    recovery_action="restore_matching_evidence",
                )
            )
    try:
        source_content = store.read(batch.source_artifact_id)
    except ArtifactStoreError:
        source_content = b""
    if hashlib.sha256(source_content).hexdigest() != batch.source_sha256:
        findings.append(
            _finding(
                "source_artifact_missing_or_corrupt",
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                artifact_id=batch.source_artifact_id,
                recoverable=False,
                recovery_action="restore_source_artifact",
            )
        )
    receipt_path = _read_path(manifest.receipt_ref)
    try:
        receipt_bytes = receipt_path.read_bytes()
    except OSError:
        receipt_bytes = b""
    code = None
    if not receipt_bytes:
        code = "receipt_file_missing"
    elif hashlib.sha256(receipt_bytes).hexdigest() != manifest.receipt_sha256:
        code = "receipt_file_hash_mismatch"
    if code is not None:
        findings.append(
            _finding(
                code,
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                artifact_id=manifest.receipt_artifact_id,
                path=str(receipt_path),
                recoverable=descriptor is not None,
                recovery_action="restore_receipt_file_from_artifact",
            )
        )
    return findings


def _expected_receipt_index_contract(
    *,
    manifest: ReceiptManifest,
    batch: ImportBatch,
    receipt_payload: dict[str, Any],
) -> dict[str, object]:
    from finharness.capital_import_registry import receipt_index_contract_fields

    return receipt_index_contract_fields(
        source_kind=batch.source_kind,
        receipt_ref=manifest.receipt_ref,
        created_at_utc=batch.as_of_utc,
        source_ref=str(receipt_payload.get("source_ref") or batch.source_id),
        upstream_receipt_id=receipt_payload.get("upstream_receipt_id"),
        source_artifact_id=batch.source_artifact_id,
    )


def _audit_manifest_mirror(
    manifest: ReceiptManifest,
    batch: ImportBatch,
    descriptor: ArtifactDescriptor | None,
    index: ReceiptIndex | None,
    snapshot: Snapshot | None,
    receipt_payload: dict[str, Any] | None = None,
) -> list[CapitalImportFinding]:
    findings: list[CapitalImportFinding] = []
    if receipt_payload is not None and batch.source_kind == "broker_read":
        expected = _expected_receipt_index_contract(
            manifest=manifest, batch=batch, receipt_payload=receipt_payload,
        )
    else:
        expected = None
    expected_kind = materialized_source_for(batch.source_kind)
    if index is None:
        findings.append(
            _finding(
                "manifest_receipt_index_missing_or_stale",
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                path=manifest.receipt_ref,
                recoverable=True,
                recovery_action="rebuild_receipt_index",
            )
        )
    else:
        if index.kind != expected_kind:
            findings.append(_finding(
                "receipt_index_kind_drift",
                batch_id=batch.batch_id, receipt_id=manifest.receipt_id,
                message="kind drift",
                recoverable=True, recovery_action="rebuild_receipt_index",
            ))
        if index.path != manifest.receipt_ref:
            findings.append(_finding(
                "receipt_index_path_drift",
                batch_id=batch.batch_id, receipt_id=manifest.receipt_id,
                path=index.path,
                message="path drift",
                recoverable=True, recovery_action="rebuild_receipt_index",
            ))
        if expected is not None:
            if index.created_at_utc != expected["created_at_utc"]:
                findings.append(_finding(
                    "receipt_index_created_at_drift",
                    batch_id=batch.batch_id, receipt_id=manifest.receipt_id,
                    recoverable=True, recovery_action="rebuild_receipt_index",
                ))
            if index.source_refs != expected["source_refs"]:
                findings.append(_finding(
                    "receipt_index_source_refs_drift",
                    batch_id=batch.batch_id, receipt_id=manifest.receipt_id,
                    recoverable=True, recovery_action="rebuild_receipt_index",
                ))
            if index.refs != expected["refs"]:
                findings.append(_finding(
                    "receipt_index_refs_drift",
                    batch_id=batch.batch_id, receipt_id=manifest.receipt_id,
                    recoverable=True, recovery_action="rebuild_receipt_index",
                ))
    if snapshot is None:
        findings.append(
            _finding(
                "materialized_snapshot_missing",
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                artifact_id=manifest.receipt_artifact_id,
                recoverable=descriptor is not None,
                recovery_action="replay_receipt",
            )
        )
    elif (
        snapshot.payload.get("record_counts") != manifest.record_counts
        or manifest.receipt_ref not in snapshot.source_refs
    ):
        findings.append(
            _finding(
                "materialized_snapshot_binding_mismatch",
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                recoverable=False,
                recovery_action="quarantine_and_reimport",
            )
        )
    return findings


def audit_capital_imports(
    *,
    engine: Engine,
    receipt_root: str | Path,
    artifact_store: ArtifactStore | None = None,
) -> CapitalImportAuditReport:
    """Classify every mismatch between immutable receipts and the queryable mirror."""
    store = artifact_store or LocalArtifactStore(Path(receipt_root) / "artifact-store")
    findings: list[CapitalImportFinding] = []
    artifact_audit = store.audit()
    for item in artifact_audit.findings:
        artifact_action = (
            "rebuild_artifact_index"
            if item.code in {"invalid_index", "stale_index", "orphan_descriptor"}
            else "restore_evidence"
        )
        findings.append(
            _finding(
                f"artifact_{item.code}",
                artifact_id=item.artifact_id,
                path=item.path,
                recoverable=item.recoverable,
                recovery_action=artifact_action,
            )
        )
    try:
        receipt_descriptors = store.list_descriptors(
            owner_domain="capital_imports", artifact_schema=RECEIPT_ARTIFACT_SCHEMA
        )
    except ArtifactStoreError:
        receipt_descriptors = ()
    descriptors_by_id = {item.artifact_id: item for item in receipt_descriptors}
    descriptors_by_batch = {
        str(item.metadata.get("batch_id")): item
        for item in receipt_descriptors
        if item.metadata.get("batch_id")
    }
    with Session(engine) as session:
        batches = list(session.exec(select(ImportBatch)).all())
        manifests = list(session.exec(select(ReceiptManifest)).all())
        receipt_indexes = list(
            session.exec(
                select(ReceiptIndex).where(col(ReceiptIndex.kind).in_(PRODUCTION_IMPORT_KINDS))
            ).all()
        )
        snapshots = {item.snapshot_id: item for item in session.exec(select(Snapshot)).all()}
    batches_by_id = {item.batch_id: item for item in batches}
    manifests_by_batch = {item.batch_id: item for item in manifests}
    manifests_by_receipt = {item.receipt_id: item for item in manifests}
    indexes_by_receipt = {item.receipt_id: item for item in receipt_indexes}

    for batch in batches:
        if batch.batch_id not in manifests_by_batch:
            findings.append(
                _finding(
                    "batch_without_manifest",
                    batch_id=batch.batch_id,
                    artifact_id=(
                        descriptors_by_batch[batch.batch_id].artifact_id
                        if batch.batch_id in descriptors_by_batch
                        else None
                    ),
                    recoverable=batch.batch_id in descriptors_by_batch,
                    recovery_action=(
                        "replay_receipt"
                        if batch.batch_id in descriptors_by_batch
                        else "restore_receipt"
                    ),
                )
            )

    for descriptor in receipt_descriptors:
        batch_id = str(descriptor.metadata.get("batch_id") or "")
        if batch_id and batch_id not in manifests_by_batch:
            findings.append(
                _finding(
                    "receipt_without_materialization",
                    batch_id=batch_id,
                    receipt_id=str(descriptor.metadata.get("receipt_id") or "") or None,
                    artifact_id=descriptor.artifact_id,
                    recoverable=True,
                    recovery_action="replay_receipt",
                )
            )

    for manifest in manifests:
        current_batch = batches_by_id.get(manifest.batch_id)
        if current_batch is None:
            findings.append(
                _finding(
                    "manifest_without_batch",
                    batch_id=manifest.batch_id,
                    receipt_id=manifest.receipt_id,
                    recoverable=False,
                    recovery_action="restore_database_backup",
                )
            )
            continue
        current_descriptor = descriptors_by_id.get(manifest.receipt_artifact_id)
        findings.extend(
            _audit_manifest_evidence(manifest, current_batch, current_descriptor, store)
        )
        rp: dict[str, Any] | None = None
        if current_descriptor is not None:
            try:
                raw = store.read(current_descriptor.artifact_id)
                rp = json.loads(raw)
            except (ArtifactStoreError, json.JSONDecodeError):
                pass
        findings.extend(
            _audit_manifest_mirror(
                manifest,
                current_batch,
                current_descriptor,
                indexes_by_receipt.get(manifest.receipt_id),
                snapshots.get(manifest.snapshot_id),
                receipt_payload=rp,
            )
        )

    for receipt_index in receipt_indexes:
        if receipt_index.receipt_id not in manifests_by_receipt:
            findings.append(
                _finding(
                    "receipt_index_without_manifest",
                    receipt_id=receipt_index.receipt_id,
                    path=receipt_index.path,
                    recoverable=True,
                    recovery_action="remove_stale_receipt_index",
                )
            )

    blocked_batches = {item.batch_id for item in findings if item.batch_id}
    verified = tuple(
        sorted(
            manifest.batch_id
            for manifest in manifests
            if manifest.batch_id not in blocked_batches
        )
    )
    ordered = tuple(
        sorted(
            findings,
            key=lambda item: (
                item.code,
                item.batch_id or "",
                item.receipt_id or "",
                item.artifact_id or "",
            ),
        )
    )
    return CapitalImportAuditReport(
        created_at_utc=datetime.now(UTC).isoformat(),
        ok=not ordered,
        batch_count=len(batches),
        manifest_count=len(manifests),
        receipt_artifact_count=len(receipt_descriptors),
        verified_batch_ids=verified,
        findings=ordered,
    )


def batch_is_verified(
    batch_id: str,
    *,
    engine: Engine,
    receipt_root: str | Path,
    artifact_store: ArtifactStore | None = None,
) -> bool:
    """Fail-closed admission helper for the authoritative resolver introduced by #258."""
    report = audit_capital_imports(
        engine=engine, receipt_root=receipt_root, artifact_store=artifact_store
    )
    return batch_id in report.verified_batch_ids


def _source_path(payload: dict[str, Any]) -> Path:
    raw = payload.get("source_ref")
    if not isinstance(raw, str) or not raw:
        raise CapitalImportRecoveryError("receipt has no replayable source_ref")
    path = _read_path(raw)
    if not path.is_file():
        raise CapitalImportRecoveryError(f"replay source is missing: {path}")
    return path


def _replay_receipt(
    descriptor: ArtifactDescriptor,
    *,
    store: ArtifactStore,
    engine: Engine,
    receipt_root: Path,
) -> str:
    payload = _receipt_payload(store, descriptor)
    kind = str(payload.get("kind") or "")
    source_path = _source_path(payload)
    if kind == "personal_finance_export":
        from finharness.personal_finance import ImportDeletion, ingest_personal_finance_export

        deletions = tuple(
            ImportDeletion(
                record_type=str(item["record_type"]),
                record_id=str(item["record_id"]),
                reason=str(item["reason"]),
            )
            for item in payload.get("deletions", [])
        )
        raw_coverage_mode = str(payload.get("coverage_mode", "full"))
        if raw_coverage_mode not in {"full", "delta"}:
            raise CapitalImportRecoveryError(
                f"receipt has invalid coverage_mode: {raw_coverage_mode}"
            )
        coverage_mode = cast(Literal["full", "delta"], raw_coverage_mode)
        ingest_personal_finance_export(
            source_path,
            engine=engine,
            receipt_root=receipt_root,
            artifact_store=store,
            snapshot_id=str(payload["snapshot_id"]),
            coverage_mode=coverage_mode,
            supersedes_batch_id=payload.get("supersedes_batch_id"),
            correction_reason=payload.get("correction_reason"),
            tombstones=deletions,
            covered_domains=payload.get("covered_domains"),
        )
    elif kind == "beancount_ledger":
        from finharness.beancount_adapter import ingest_beancount_ledger

        ingest_beancount_ledger(
            source_path,
            engine=engine,
            receipt_root=receipt_root,
            artifact_store=store,
            snapshot_id=str(payload["snapshot_id"]),
        )
    elif kind == "broker_read":
        from finharness.statecore.snapshot_ingest import ingest_broker_read_receipt

        ingest_broker_read_receipt(
            source_path,
            engine=engine,
            receipt_root=receipt_root,
            artifact_store=store,
            snapshot_id=str(payload["snapshot_id"]),
        )
    else:
        raise CapitalImportRecoveryError(f"unsupported replay import kind: {kind}")
    return f"replayed:{descriptor.artifact_id}"


def _repair_artifact_index(
    before: CapitalImportAuditReport, store: ArtifactStore
) -> list[str]:
    repairable_codes = {
        "artifact_invalid_index",
        "artifact_stale_index",
        "artifact_orphan_descriptor",
    }
    if not any(item.code in repairable_codes for item in before.findings):
        return []
    if not isinstance(store, ArtifactRecoveryPort):
        raise CapitalImportRecoveryError(
            "artifact store does not expose deterministic index recovery"
        )
    store.recover_index()
    return ["rebuilt_artifact_index"]


def recover_capital_imports(
    *,
    engine: Engine,
    receipt_root: str | Path,
    artifact_store: ArtifactStore | None = None,
    dry_run: bool = False,
) -> CapitalImportRecoveryReceipt:
    """Apply only deterministic repairs, retain evidence, and emit a recovery receipt."""
    root = Path(receipt_root)
    store = artifact_store or LocalArtifactStore(root / "artifact-store")
    before = audit_capital_imports(engine=engine, receipt_root=root, artifact_store=store)
    actions: list[str] = []
    if not dry_run:
        actions.extend(_repair_artifact_index(before, store))

        with Session(engine) as session:
            manifests = list(session.exec(select(ReceiptManifest)).all())
            batches = {item.batch_id: item for item in session.exec(select(ImportBatch)).all()}
            for manifest in manifests:
                try:
                    content = store.read(manifest.receipt_artifact_id)
                except ArtifactStoreError:
                    continue
                target = _read_path(manifest.receipt_ref)
                try:
                    target.resolve().relative_to(root.resolve())
                except ValueError:
                    continue
                if (
                    not target.is_file()
                    or hashlib.sha256(target.read_bytes()).hexdigest() != manifest.receipt_sha256
                ):
                    atomic_write_bytes(target, content)
                    actions.append(f"restored_receipt_file:{manifest.receipt_id}")
                current_index = session.get(ReceiptIndex, manifest.receipt_id)
                payload = json.loads(content)
                batch = batches[manifest.batch_id]
                source_ref = str(payload.get("source_ref") or batch.source_id)
                upstream_id = payload.get("upstream_receipt_id")
                from finharness.capital_import_registry import receipt_index_contract_fields

                contract = receipt_index_contract_fields(
                    source_kind=batch.source_kind,
                    receipt_ref=manifest.receipt_ref,
                    created_at_utc=batch.as_of_utc,
                    source_ref=source_ref,
                    upstream_receipt_id=upstream_id,
                    source_artifact_id=batch.source_artifact_id,
                )
                needs_rebuild = (
                    current_index is None
                    or current_index.kind != contract["kind"]
                    or current_index.path != contract["path"]
                    or current_index.created_at_utc != contract["created_at_utc"]
                    or current_index.source_refs != contract["source_refs"]
                    or current_index.refs != contract["refs"]
                )
                if needs_rebuild:
                    session.merge(
                        ReceiptIndex(
                            receipt_id=manifest.receipt_id,
                            kind=cast(str, contract["kind"]),
                            path=cast(str, contract["path"]),
                            created_at_utc=cast(str, contract["created_at_utc"]),
                            source_refs=cast(list[str], contract["source_refs"]),
                            refs=cast(list[str], contract["refs"]),
                        )
                    )
                    actions.append(f"rebuilt_receipt_index:{manifest.receipt_id}")
            session.commit()

        refreshed = audit_capital_imports(
            engine=engine, receipt_root=root, artifact_store=store
        )
        replay_ids = sorted(
            {
                item.artifact_id
                for item in refreshed.findings
                if item.recovery_action == "replay_receipt" and item.artifact_id
            }
        )
        descriptors = {item.artifact_id: item for item in store.list_descriptors()}
        for artifact_id in replay_ids:
            try:
                actions.append(
                    _replay_receipt(
                        descriptors[artifact_id], store=store, engine=engine, receipt_root=root
                    )
                )
            except (CapitalImportRecoveryError, KeyError, OSError, ValueError):
                continue

        with Session(engine) as session:
            manifested_ids = set(session.exec(select(ReceiptManifest.receipt_id)).all())
            stale = list(
                session.exec(
                    select(ReceiptIndex).where(
                        col(ReceiptIndex.kind).in_(PRODUCTION_IMPORT_KINDS),
                        col(ReceiptIndex.receipt_id).not_in(manifested_ids),
                    )
                ).all()
            )
            for item in stale:
                session.execute(
                    delete(ReceiptIndex).where(col(ReceiptIndex.receipt_id) == item.receipt_id)
                )
                actions.append(f"removed_stale_receipt_index:{item.receipt_id}")
            session.commit()

    after = (
        audit_capital_imports(engine=engine, receipt_root=root, artifact_store=store)
        if not dry_run
        else before
    )
    created_at = datetime.now(UTC).isoformat()
    recovery_digest = hashlib.sha256(
        (created_at + str(before.model_dump())).encode()
    ).hexdigest()[:24]
    recovery_id = f"capital_import_recovery_{recovery_digest}"
    receipt = CapitalImportRecoveryReceipt(
        recovery_id=recovery_id,
        created_at_utc=created_at,
        dry_run=dry_run,
        before=before,
        after=after,
        actions=tuple(actions),
        unresolved_findings=after.findings,
    )
    if not dry_run:
        payload = receipt.model_dump(mode="json", by_alias=True)
        content = canonical_json_bytes(payload)
        path = resolve_under(root, "recovery", f"{recovery_id}.json")
        atomic_write_json(path, payload)
        store.put(
            artifact_id=recovery_id,
            content=content,
            artifact_schema=CAPITAL_IMPORT_RECOVERY_ARTIFACT_SCHEMA,
            artifact_schema_version=CAPITAL_IMPORT_RECOVERY_SCHEMA,
            media_type="application/json",
            owner_domain="capital_imports",
            source_refs=tuple(
                sorted(
                    item.artifact_id
                    for item in before.findings
                    if item.artifact_id is not None
                )
            ),
            metadata={"recovery_id": recovery_id, "after_ok": after.ok},
            created_at_utc=created_at,
        )
    return receipt
