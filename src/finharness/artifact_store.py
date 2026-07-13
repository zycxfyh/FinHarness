"""Shared immutable Artifact/Receipt Store contract and local implementation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finharness.statecore.receipt_io import atomic_write_bytes, atomic_write_json, resolve_under

ARTIFACT_DESCRIPTOR_SCHEMA = "finharness.artifact_descriptor.v1"
ARTIFACT_INDEX_SCHEMA = "finharness.artifact_index.v1"
ARTIFACT_RECOVERY_SCHEMA = "finharness.artifact_recovery_receipt.v1"


class ArtifactStoreError(RuntimeError):
    """Base error for integrity or durability failures."""


class ArtifactConflictError(ArtifactStoreError):
    """An artifact id was reused with different immutable content or metadata."""


class ArtifactNotFoundError(ArtifactStoreError):
    """The requested artifact descriptor or bytes are missing."""


class ArtifactDescriptor(BaseModel):
    """Domain-neutral integrity envelope; domains continue to own payload semantics."""

    model_config = ConfigDict(frozen=True)

    descriptor_schema: str = ARTIFACT_DESCRIPTOR_SCHEMA
    artifact_id: str
    artifact_schema: str
    artifact_schema_version: str
    content_sha256: str
    content_length: int
    media_type: str
    owner_domain: str
    created_at_utc: str
    source_refs: tuple[str, ...] = ()
    metadata: dict[str, Any]

    @field_validator(
        "artifact_id",
        "artifact_schema",
        "artifact_schema_version",
        "media_type",
        "owner_domain",
    )
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("artifact identity and schema fields must be non-empty")
        return value.strip()

    @field_validator("content_sha256")
    @classmethod
    def require_sha256(cls, value: str) -> str:
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("content_sha256 must be lowercase SHA-256")
        return value


class ArtifactFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    artifact_id: str | None = None
    path: str | None = None
    message: str
    recoverable: bool


class ArtifactAuditReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    descriptor_count: int
    indexed_count: int
    object_count: int
    findings: tuple[ArtifactFinding, ...]


class ArtifactRecoveryReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    receipt_schema: str = Field(
        default=ARTIFACT_RECOVERY_SCHEMA,
        validation_alias="schema",
        serialization_alias="schema",
    )
    recovery_id: str
    created_at_utc: str
    dry_run: bool
    before: ArtifactAuditReport
    after: ArtifactAuditReport
    repaired_artifact_ids: tuple[str, ...]
    unresolved_findings: tuple[ArtifactFinding, ...]


@runtime_checkable
class ArtifactStore(Protocol):
    """Durability/integrity port used by domain services."""

    def put(
        self,
        *,
        artifact_id: str,
        content: bytes,
        artifact_schema: str,
        artifact_schema_version: str,
        media_type: str,
        owner_domain: str,
        source_refs: tuple[str, ...] = (),
        metadata: Mapping[str, Any] | None = None,
        created_at_utc: str | None = None,
    ) -> ArtifactDescriptor: ...

    def descriptor(self, artifact_id: str) -> ArtifactDescriptor: ...

    def read(self, artifact_id: str) -> bytes: ...

    def audit(
        self, *, expected_schemas: Mapping[str, set[str]] | None = None
    ) -> ArtifactAuditReport: ...


@runtime_checkable
class ArtifactRecoveryPort(Protocol):
    """Index/recovery port shared by future domain migrations."""

    def recover_index(self, *, dry_run: bool = False) -> ArtifactRecoveryReceipt: ...


class LocalArtifactStore:
    """Filesystem-backed immutable content store with reconstructable JSON index."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put(
        self,
        *,
        artifact_id: str,
        content: bytes,
        artifact_schema: str,
        artifact_schema_version: str,
        media_type: str,
        owner_domain: str,
        source_refs: tuple[str, ...] = (),
        metadata: Mapping[str, Any] | None = None,
        created_at_utc: str | None = None,
    ) -> ArtifactDescriptor:
        content_hash = hashlib.sha256(content).hexdigest()
        descriptor = ArtifactDescriptor(
            artifact_id=artifact_id,
            artifact_schema=artifact_schema,
            artifact_schema_version=artifact_schema_version,
            content_sha256=content_hash,
            content_length=len(content),
            media_type=media_type,
            owner_domain=owner_domain,
            created_at_utc=created_at_utc or datetime.now(UTC).isoformat(),
            source_refs=source_refs,
            metadata=dict(metadata or {}),
        )
        descriptor_path = self._descriptor_path(artifact_id)
        object_path = self._object_path(content_hash)
        if descriptor_path.exists():
            existing = self.descriptor(artifact_id)
            if existing != descriptor:
                raise ArtifactConflictError(f"artifact id {artifact_id!r} is immutable")
            if self.read(artifact_id) != content:
                raise ArtifactConflictError(f"artifact bytes for {artifact_id!r} changed")
            return existing
        if object_path.exists() and object_path.read_bytes() != content:
            raise ArtifactConflictError(f"SHA-256 object collision for {content_hash}")
        self._write_bytes_once(object_path, content)
        atomic_write_json(descriptor_path, descriptor.model_dump(mode="json"))
        self._write_index(self._descriptor_map())
        return descriptor

    def descriptor(self, artifact_id: str) -> ArtifactDescriptor:
        path = self._descriptor_path(artifact_id)
        try:
            return ArtifactDescriptor.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ArtifactNotFoundError(f"artifact descriptor not found: {artifact_id}") from exc

    def read(self, artifact_id: str) -> bytes:
        descriptor = self.descriptor(artifact_id)
        path = self._object_path(descriptor.content_sha256)
        try:
            content = path.read_bytes()
        except FileNotFoundError as exc:
            raise ArtifactNotFoundError(f"artifact bytes not found: {artifact_id}") from exc
        if hashlib.sha256(content).hexdigest() != descriptor.content_sha256:
            raise ArtifactStoreError(f"artifact content hash mismatch: {artifact_id}")
        return content

    def audit(
        self, *, expected_schemas: Mapping[str, set[str]] | None = None
    ) -> ArtifactAuditReport:
        findings: list[ArtifactFinding] = []
        descriptors = self._load_descriptors(findings)
        index = self._load_index(findings)
        objects = set(self._iter_object_hashes())
        referenced_objects: set[str] = set()
        for artifact_id, descriptor in descriptors.items():
            referenced_objects.add(descriptor.content_sha256)
            object_path = self._object_path(descriptor.content_sha256)
            if not object_path.is_file():
                findings.append(self._finding("missing_bytes", artifact_id, object_path, True))
            else:
                content = object_path.read_bytes()
                if hashlib.sha256(content).hexdigest() != descriptor.content_sha256:
                    findings.append(
                        self._finding("content_hash_mismatch", artifact_id, object_path, False)
                    )
                if len(content) != descriptor.content_length:
                    findings.append(
                        self._finding("content_length_mismatch", artifact_id, object_path, False)
                    )
            allowed_versions = (expected_schemas or {}).get(descriptor.artifact_schema)
            if (
                allowed_versions is not None
                and descriptor.artifact_schema_version not in allowed_versions
            ):
                findings.append(self._finding("schema_version_mismatch", artifact_id, None, False))
            if artifact_id not in index:
                findings.append(self._finding("orphan_descriptor", artifact_id, None, True))
            elif index[artifact_id] != descriptor.content_sha256:
                findings.append(self._finding("stale_index", artifact_id, None, True))
        for artifact_id in sorted(set(index) - set(descriptors)):
            findings.append(self._finding("stale_index", artifact_id, None, True))
        for content_hash in sorted(objects - referenced_objects):
            findings.append(
                self._finding("orphan_bytes", None, self._object_path(content_hash), False)
            )
        return ArtifactAuditReport(
            ok=not findings,
            descriptor_count=len(descriptors),
            indexed_count=len(index),
            object_count=len(objects),
            findings=tuple(findings),
        )

    def recover_index(self, *, dry_run: bool = False) -> ArtifactRecoveryReceipt:
        before = self.audit()
        descriptors = self._descriptor_map()
        repaired = tuple(sorted(descriptors))
        if not dry_run:
            self._write_index(descriptors)
        after = self.audit() if not dry_run else before
        recovery_id = f"artifact_recovery_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}"
        receipt = ArtifactRecoveryReceipt(
            recovery_id=recovery_id,
            created_at_utc=datetime.now(UTC).isoformat(),
            dry_run=dry_run,
            before=before,
            after=after,
            repaired_artifact_ids=repaired,
            unresolved_findings=tuple(
                finding for finding in after.findings if not finding.recoverable
            ),
        )
        if not dry_run:
            atomic_write_json(
                resolve_under(self.root, "recovery", f"{recovery_id}.json"),
                receipt.model_dump(mode="json", by_alias=True),
            )
        return receipt

    def _descriptor_path(self, artifact_id: str) -> Path:
        return resolve_under(self.root, "descriptors", f"{artifact_id}.json")

    def _object_path(self, content_hash: str) -> Path:
        return resolve_under(self.root, "objects", content_hash[:2], f"{content_hash}.bin")

    def _write_bytes_once(self, path: Path, content: bytes) -> None:
        if path.exists():
            return
        atomic_write_bytes(path, content)

    def _load_descriptors(self, findings: list[ArtifactFinding]) -> dict[str, ArtifactDescriptor]:
        result: dict[str, ArtifactDescriptor] = {}
        root = resolve_under(self.root, "descriptors")
        for path in sorted(root.glob("*.json")) if root.is_dir() else ():
            try:
                descriptor = ArtifactDescriptor.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                findings.append(self._finding("invalid_descriptor", None, path, False))
                continue
            result[descriptor.artifact_id] = descriptor
        return result

    def _descriptor_map(self) -> dict[str, ArtifactDescriptor]:
        findings: list[ArtifactFinding] = []
        descriptors = self._load_descriptors(findings)
        if findings:
            raise ArtifactStoreError("invalid descriptors prevent index recovery")
        return descriptors

    def _load_index(self, findings: list[ArtifactFinding]) -> dict[str, str]:
        path = resolve_under(self.root, "index.json")
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema") != ARTIFACT_INDEX_SCHEMA:
                raise ValueError("unsupported index schema")
            return {str(key): str(value) for key, value in payload["artifacts"].items()}
        except (OSError, ValueError, TypeError, KeyError):
            findings.append(self._finding("invalid_index", None, path, True))
            return {}

    def _write_index(self, descriptors: Mapping[str, ArtifactDescriptor]) -> None:
        atomic_write_json(
            resolve_under(self.root, "index.json"),
            {
                "schema": ARTIFACT_INDEX_SCHEMA,
                "artifacts": {
                    artifact_id: descriptor.content_sha256
                    for artifact_id, descriptor in sorted(descriptors.items())
                },
            },
        )

    def _iter_object_hashes(self) -> tuple[str, ...]:
        root = resolve_under(self.root, "objects")
        if not root.is_dir():
            return ()
        return tuple(path.stem for path in root.glob("*/*.bin"))

    def _finding(
        self,
        code: str,
        artifact_id: str | None,
        path: Path | None,
        recoverable: bool,
    ) -> ArtifactFinding:
        return ArtifactFinding(
            code=code,
            artifact_id=artifact_id,
            path=str(path.relative_to(self.root)) if path is not None else None,
            message=code.replace("_", " "),
            recoverable=recoverable,
        )
