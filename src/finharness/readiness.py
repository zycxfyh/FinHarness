"""Bounded, non-mutating operational and capital-truth readiness probes."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, text
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import SQLAlchemyError

from finharness.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    LocalArtifactStore,
)
from finharness.statecore.receipt_io import resolve_under
from finharness.statecore.store import CURRENT_STATE_CORE_USER_VERSION

_REQUIRED_TABLES = frozenset({"import_batches", "receipt_manifests", "receipt_index", "snapshots"})
_CAPITAL_MAX_AGE = timedelta(hours=24)
TruthCategory = Literal["missing", "corrupt", "stale", "partial", "unavailable"]


class _QueryConnection(Protocol):
    def execute(self, statement: Any, parameters: Any = None) -> Any: ...


class ReadinessCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    detail: str


class OperationalReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ready", "not_ready"]
    checks: dict[str, ReadinessCheck]
    execution_allowed: Literal[False] = False
    non_claims: tuple[str, ...] = (
        "Operational dependency check only.",
        "Not capital truth readiness.",
        "Not execution authorization.",
    )


class TruthFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    category: TruthCategory
    detail: str


class CapitalTruthReadiness(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["usable", "partial", "blocked", "unavailable"]
    current: bool
    verified: bool
    checked_manifest_id: str | None
    findings: tuple[TruthFinding, ...]
    execution_allowed: Literal[False] = False
    non_claims: tuple[str, ...] = (
        "Bounded latest-import evidence check only.",
        "Not accounting reconciliation.",
        "Not execution authorization.",
    )


def _path_capability(path: Path) -> ReadinessCheck:
    """Inspect filesystem capability without creating a probe file or directory."""
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    try:
        mode = candidate.stat().st_mode
    except OSError as exc:
        return ReadinessCheck(status="unavailable", detail=str(exc))
    if not candidate.is_dir():
        return ReadinessCheck(status="unavailable", detail=f"not a directory: {candidate}")
    writable_mode = bool(mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    if not writable_mode or not os.access(candidate, os.R_OK | os.W_OK | os.X_OK):
        return ReadinessCheck(
            status="unwritable",
            detail=f"receipt storage is not readable and writable: {candidate}",
        )
    detail = "storage root is readable and writable"
    if candidate != path:
        detail = f"storage root is creatable under {candidate}"
    return ReadinessCheck(status="ready", detail=detail)


@contextmanager
def _connection(*, engine: Engine | None, db_path: Path) -> Iterator[tuple[_QueryConnection, bool]]:
    if engine is not None:
        with engine.connect() as sa_connection:
            yield sa_connection, True
        return
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    sqlite_connection = sqlite3.connect(uri, uri=True)
    sqlite_connection.row_factory = sqlite3.Row
    try:
        yield sqlite_connection, False
    finally:
        sqlite_connection.close()


def _scalar(connection: _QueryConnection, sqlalchemy_connection: bool, query: str) -> Any:
    if sqlalchemy_connection:
        return connection.execute(text(query)).scalar_one()
    row = connection.execute(query).fetchone()
    return None if row is None else row[0]


def _mapping(
    connection: _QueryConnection, sqlalchemy_connection: bool, query: str
) -> Mapping[str, Any] | None:
    if sqlalchemy_connection:
        row: RowMapping | None = connection.execute(text(query)).mappings().first()
        return None if row is None else dict(row)
    row = connection.execute(query).fetchone()
    return None if row is None else dict(row)


def _state_core_check(*, engine: Engine | None, db_path: Path) -> ReadinessCheck:
    if engine is None and not db_path.is_file():
        return ReadinessCheck(status="missing", detail=f"state-core database missing: {db_path}")
    try:
        with _connection(engine=engine, db_path=db_path) as (connection, is_sa):
            integrity = str(_scalar(connection, is_sa, "PRAGMA quick_check(1)"))
            if integrity.lower() != "ok":
                return ReadinessCheck(status="corrupt", detail=f"integrity check: {integrity}")
            version = int(_scalar(connection, is_sa, "PRAGMA user_version"))
            table_rows = connection.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
                if is_sa
                else "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            tables = {str(row[0]) for row in table_rows}
            missing = sorted(_REQUIRED_TABLES - tables)
            if missing or version != CURRENT_STATE_CORE_USER_VERSION:
                detail = f"schema version {version}; missing tables: {missing}"
                return ReadinessCheck(status="schema_incomplete", detail=detail)
    except (OSError, sqlite3.DatabaseError, SQLAlchemyError, ValueError) as exc:
        return ReadinessCheck(status="corrupt", detail=str(exc))
    return ReadinessCheck(status="ready", detail="state-core is readable and current")


def operational_readiness(
    *, engine: Engine | None, db_path: Path, receipt_root: Path
) -> OperationalReadiness:
    checks = {
        "state_core": _state_core_check(engine=engine, db_path=db_path),
        "receipt_storage": _path_capability(receipt_root),
    }
    ready = all(check.status == "ready" for check in checks.values())
    return OperationalReadiness(status="ready" if ready else "not_ready", checks=checks)


_LATEST_IMPORT_QUERY = """
SELECT
    m.manifest_id,
    m.receipt_id,
    m.receipt_ref,
    m.receipt_sha256,
    m.receipt_artifact_id,
    m.source_artifact_id AS manifest_source_artifact_id,
    m.snapshot_id,
    b.source_artifact_id,
    b.source_sha256,
    b.completeness_status,
    b.time_semantics,
    r.path AS indexed_receipt_ref,
    s.as_of_utc AS snapshot_as_of_utc
FROM receipt_manifests AS m
JOIN import_batches AS b ON b.batch_id = m.batch_id
LEFT JOIN receipt_index AS r ON r.receipt_id = m.receipt_id
LEFT JOIN snapshots AS s ON s.snapshot_id = m.snapshot_id
ORDER BY m.materialized_at_utc DESC, m.manifest_id DESC
LIMIT 1
"""


def _finding(code: str, category: TruthCategory, detail: str) -> TruthFinding:
    return TruthFinding(code=code, category=category, detail=detail)


def _parse_observed_at(row: Mapping[str, Any]) -> datetime | None:
    import json

    try:
        semantics = row["time_semantics"]
        if isinstance(semantics, str):
            semantics = json.loads(semantics)
        value = semantics.get("observed_at_utc") or row["snapshot_as_of_utc"]
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.utcoffset() is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def _binding_findings(row: Mapping[str, Any], receipt_root: Path) -> list[TruthFinding]:
    findings: list[TruthFinding] = []
    if row["indexed_receipt_ref"] != row["receipt_ref"]:
        findings.append(
            _finding(
                "receipt_index_missing_or_divergent",
                "missing",
                "receipt index binding failed",
            )
        )
    if row["snapshot_as_of_utc"] is None:
        findings.append(_finding("snapshot_missing", "missing", "manifest snapshot is absent"))
    if row["manifest_source_artifact_id"] != row["source_artifact_id"]:
        findings.append(
            _finding("source_binding_corrupt", "corrupt", "manifest and batch source differ")
        )
    receipt_path = resolve_under(receipt_root, f"{row['receipt_id']}.json")
    try:
        receipt_bytes = receipt_path.read_bytes()
        if hashlib.sha256(receipt_bytes).hexdigest() != row["receipt_sha256"]:
            findings.append(_finding("receipt_hash_mismatch", "corrupt", "receipt hash differs"))
    except FileNotFoundError:
        findings.append(_finding("receipt_file_missing", "missing", str(receipt_path)))
    except OSError as exc:
        findings.append(_finding("receipt_file_unavailable", "unavailable", str(exc)))
    return findings


def _artifact_findings(row: Mapping[str, Any], receipt_root: Path) -> list[TruthFinding]:
    findings: list[TruthFinding] = []
    store = LocalArtifactStore(receipt_root / "artifact-store")
    try:
        source_descriptor = store.descriptor(str(row["source_artifact_id"]))
        store.read(str(row["source_artifact_id"]))
        if source_descriptor.content_sha256 != row["source_sha256"]:
            findings.append(
                _finding("source_artifact_hash_mismatch", "corrupt", "source hash differs")
            )
    except ArtifactNotFoundError as exc:
        findings.append(_finding("source_artifact_missing_or_corrupt", "missing", str(exc)))
    except ArtifactStoreError as exc:
        findings.append(_finding("source_artifact_missing_or_corrupt", "corrupt", str(exc)))
    try:
        receipt_descriptor = store.descriptor(str(row["receipt_artifact_id"]))
        store.read(str(row["receipt_artifact_id"]))
        if receipt_descriptor.content_sha256 != row["receipt_sha256"]:
            findings.append(
                _finding("receipt_artifact_hash_mismatch", "corrupt", "artifact hash differs")
            )
    except ArtifactNotFoundError as exc:
        findings.append(_finding("receipt_artifact_missing_or_corrupt", "missing", str(exc)))
    except ArtifactStoreError as exc:
        findings.append(_finding("receipt_artifact_missing_or_corrupt", "corrupt", str(exc)))
    return findings


def capital_truth_readiness(
    *,
    engine: Engine | None,
    db_path: Path,
    receipt_root: Path,
    evaluated_at: datetime | None = None,
) -> CapitalTruthReadiness:
    db_check = _state_core_check(engine=engine, db_path=db_path)
    if db_check.status != "ready":
        return CapitalTruthReadiness(
            status="unavailable",
            current=False,
            verified=False,
            checked_manifest_id=None,
            findings=(_finding("state_core_unavailable", "unavailable", db_check.detail),),
        )
    try:
        with _connection(engine=engine, db_path=db_path) as (connection, is_sa):
            row = _mapping(connection, is_sa, _LATEST_IMPORT_QUERY)
    except (OSError, sqlite3.DatabaseError, SQLAlchemyError) as exc:
        return CapitalTruthReadiness(
            status="unavailable",
            current=False,
            verified=False,
            checked_manifest_id=None,
            findings=(_finding("state_core_query_failed", "unavailable", str(exc)),),
        )
    if row is None:
        return CapitalTruthReadiness(
            status="blocked",
            current=False,
            verified=False,
            checked_manifest_id=None,
            findings=(
                _finding("capital_import_missing", "missing", "no materialized import found"),
            ),
        )

    findings = _binding_findings(row, receipt_root)
    manifest_id = str(row["manifest_id"])

    observed_at = _parse_observed_at(row)
    now = (evaluated_at or datetime.now(UTC)).astimezone(UTC)
    age = None if observed_at is None else now - observed_at
    current = age is not None and timedelta(0) <= age <= _CAPITAL_MAX_AGE
    if observed_at is None:
        findings.append(_finding("observation_time_missing", "missing", "canonical clock missing"))
    elif age is not None and age < timedelta(0):
        findings.append(
            _finding("capital_snapshot_in_future", "corrupt", "observation is in the future")
        )
    elif not current:
        findings.append(_finding("capital_snapshot_stale", "stale", "observation exceeds 24 hours"))

    findings.extend(_artifact_findings(row, receipt_root))

    completeness = str(row["completeness_status"])
    if completeness == "partial":
        findings.append(_finding("capital_import_partial", "partial", "latest import is partial"))
    elif completeness != "complete":
        findings.append(
            _finding("capital_import_blocked", "partial", f"latest import is {completeness}")
        )

    blocking_categories = {"missing", "corrupt", "stale", "unavailable"}
    blocked = any(finding.category in blocking_categories for finding in findings)
    status: Literal["usable", "partial", "blocked", "unavailable"]
    status = (
        "blocked"
        if blocked or completeness not in {"complete", "partial"}
        else ("partial" if findings else "usable")
    )
    return CapitalTruthReadiness(
        status=status,
        current=current,
        verified=not blocked,
        checked_manifest_id=manifest_id,
        findings=tuple(findings),
    )
