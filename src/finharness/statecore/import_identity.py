"""Receipt-bound proof for capital-import materialized rows and content."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select as sa_select
from sqlmodel import Session, SQLModel

MATERIALIZED_RECORD_IDENTITIES_FIELD = "materialized_record_identities"
MATERIALIZED_RECORD_CONTENT_SCHEMA = "finharness.materialized_record_content.v1"

TABLE_DOMAINS: dict[str, str] = {
    "receipt_index": "receipt",
    "account_identities": "account",
    "instrument_identities": "position",
    "identity_aliases": "identity",
    "accounts": "account",
    "snapshots": "snapshot",
    "positions": "position",
    "liabilities": "liability",
    "financial_goals": "goal",
    "cashflow_events": "cashflow",
    "tax_events": "tax_event",
    "insurance_policies": "insurance",
    "document_refs": "document",
}
OWNER_SCOPED_TABLES: dict[str, str] = {
    "liabilities": "liability",
    "financial_goals": "goal",
    "cashflow_events": "cashflow",
    "tax_events": "tax_event",
    "insurance_policies": "insurance",
    "document_refs": "document",
}
HISTORICAL_REPLAY_ALLOWED_TABLES = frozenset(
    {"receipt_index", "snapshots", "positions"}
)
CURRENT_REPLAY_TABLE_DOMAINS: dict[str, frozenset[str]] = {
    "account_identities": frozenset({"account", "position"}),
    "instrument_identities": frozenset({"position"}),
    "identity_aliases": frozenset({"account", "position"}),
    "accounts": frozenset({"account", "position"}),
    **{table: frozenset({domain}) for table, domain in OWNER_SCOPED_TABLES.items()},
}


class MaterializedRecordIdentityError(RuntimeError):
    """Raised when receipt-bound materialized proof is malformed."""


@dataclass(frozen=True)
class MaterializedIdentityMismatch:
    code: str
    table: str
    record_id: str
    message: str


def _identity_sort_key(item: Mapping[str, str]) -> tuple[str, str, str]:
    return (item["table"], item["record_id"], item.get("scope_id", ""))


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, float):
        return {"$float": repr(value)}
    if isinstance(value, datetime):
        return {"$datetime": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, UUID):
        return {"$uuid": str(value)}
    if isinstance(value, Enum):
        return _canonical_value(value.value)
    if isinstance(value, bytes):
        return {"$bytes_base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    raise MaterializedRecordIdentityError(
        f"unsupported materialized content value: {type(value).__name__}"
    )



def _stable_receipt_reference(value: str) -> str:
    name = Path(value).name
    if name.startswith("receipt_") and name.endswith(".json"):
        return f"receipt://{name[:-5]}"
    return value


def _normalize_lineage_value(key: str, value: Any) -> Any:
    if key == "import_receipt_ref" and isinstance(value, str):
        return _stable_receipt_reference(value)
    if key == "source_refs" and isinstance(value, list):
        return [
            _stable_receipt_reference(item) if isinstance(item, str) else item
            for item in value
        ]
    if isinstance(value, Mapping):
        return {
            str(child_key): _normalize_lineage_value(str(child_key), child_value)
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_normalize_lineage_value("", item) for item in value]
    return value


def _content_commitment_payload(table_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = {
        key: _normalize_lineage_value(key, value) for key, value in payload.items()
    }
    if table_name == "receipt_index" and isinstance(normalized.get("path"), str):
        normalized["path"] = _stable_receipt_reference(normalized["path"])
    return normalized

def _content_digest(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _record_content_payload(record: Any) -> dict[str, Any]:
    table = getattr(record.__class__, "__table__", None)
    if table is None:
        raise MaterializedRecordIdentityError(
            f"materialized record {record.__class__.__name__} has no table"
        )
    payload = {column.name: getattr(record, column.name) for column in table.columns}
    return _content_commitment_payload(table.name, payload)


def _row_content_digest(table_name: str, row: Any) -> str:
    table = SQLModel.metadata.tables[table_name]
    payload = {column.name: row[column.name] for column in table.columns}
    return _content_digest(_content_commitment_payload(table_name, payload))


def materialized_record_identity(record: Any) -> dict[str, str] | None:
    """Return deterministic identity and content commitment for one materialized row."""
    table = getattr(record.__class__, "__table__", None)
    if table is None or table.name not in TABLE_DOMAINS:
        return None
    primary_keys = list(table.primary_key.columns)
    if len(primary_keys) != 1:
        raise MaterializedRecordIdentityError(
            f"capital import table {table.name!r} must have exactly one primary key"
        )
    primary_key = primary_keys[0].name
    record_id = str(getattr(record, primary_key, "") or "").strip()
    if not record_id:
        raise MaterializedRecordIdentityError(
            f"capital import record {record.__class__.__name__} has no primary-key identity"
        )
    identity = {
        "record_type": record.__class__.__name__,
        "table": table.name,
        "primary_key": primary_key,
        "record_id": record_id,
        "domain": TABLE_DOMAINS[table.name],
        "content_schema": MATERIALIZED_RECORD_CONTENT_SCHEMA,
        "content_sha256": _content_digest(_record_content_payload(record)),
    }
    if table.name == "positions":
        identity["scope_id"] = str(getattr(record, "snapshot_id", "") or "")
    return identity


def materialized_record_identities(records: Iterable[Any]) -> list[dict[str, str]]:
    """Freeze exact row identities and canonical persisted content commitments."""
    identities = [
        identity
        for record in records
        if (identity := materialized_record_identity(record)) is not None
    ]
    identities.sort(key=_identity_sort_key)
    keys = {(item["table"], item["record_id"]) for item in identities}
    if len(keys) != len(identities):
        raise MaterializedRecordIdentityError(
            "materialized record proof contains duplicate table identities"
        )
    return identities


def normalize_materialized_record_identities(  # noqa: C901
    raw: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, str]]:
    """Validate and normalize immutable receipt row proof."""
    if raw is None:
        raise MaterializedRecordIdentityError("receipt has no materialized record proof")
    normalized: list[dict[str, str]] = []
    for item in raw:
        table_name = str(item.get("table") or "").strip()
        if table_name not in TABLE_DOMAINS:
            raise MaterializedRecordIdentityError(
                f"unsupported materialized identity table: {table_name!r}"
            )
        table = SQLModel.metadata.tables.get(table_name)
        primary_keys = list(table.primary_key.columns) if table is not None else []
        if len(primary_keys) != 1:
            raise MaterializedRecordIdentityError(
                f"materialized identity table {table_name!r} has no unique primary key"
            )
        expected_primary_key = primary_keys[0].name
        entry = {
            "record_type": str(item.get("record_type") or "").strip(),
            "table": table_name,
            "primary_key": str(item.get("primary_key") or "").strip(),
            "record_id": str(item.get("record_id") or "").strip(),
            "domain": str(item.get("domain") or "").strip(),
            "content_schema": str(item.get("content_schema") or "").strip(),
            "content_sha256": str(item.get("content_sha256") or "").strip().lower(),
        }
        scope_id = str(item.get("scope_id") or "").strip()
        if scope_id:
            entry["scope_id"] = scope_id
        if not entry["record_type"] or not entry["record_id"]:
            raise MaterializedRecordIdentityError(
                "materialized identity requires record_type and record_id"
            )
        if entry["primary_key"] != expected_primary_key:
            raise MaterializedRecordIdentityError(
                f"materialized identity primary key mismatch for {table_name}"
            )
        if entry["domain"] != TABLE_DOMAINS[table_name]:
            raise MaterializedRecordIdentityError(
                f"materialized identity domain mismatch for {table_name}"
            )
        if entry["content_schema"] != MATERIALIZED_RECORD_CONTENT_SCHEMA:
            raise MaterializedRecordIdentityError(
                f"materialized content schema mismatch for {table_name}"
            )
        digest = entry["content_sha256"]
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise MaterializedRecordIdentityError(
                f"materialized content digest is invalid for {table_name}"
            )
        if table_name == "positions" and not scope_id:
            raise MaterializedRecordIdentityError(
                "position materialized identity requires snapshot scope_id"
            )
        normalized.append(entry)
    normalized.sort(key=_identity_sort_key)
    keys = {(item["table"], item["record_id"]) for item in normalized}
    if len(keys) != len(normalized):
        raise MaterializedRecordIdentityError(
            "materialized record proof contains duplicate table identities"
        )
    return normalized


def audit_materialized_record_identities(  # noqa: C901
    session: Session,
    *,
    source_kind: str,
    source_id: str,
    expected: Sequence[Mapping[str, Any]],
    current_domains: set[str],
) -> list[MaterializedIdentityMismatch]:
    """Compare receipt-bound identity/content proof with the queryable mirror."""
    normalized = normalize_materialized_record_identities(expected)
    owner = f"{source_kind}::{source_id}"
    findings: list[MaterializedIdentityMismatch] = []
    expected_by_table: dict[str, set[str]] = {}
    for identity in normalized:
        table_name = identity["table"]
        required_domains = CURRENT_REPLAY_TABLE_DOMAINS.get(table_name)
        if required_domains and not required_domains & current_domains:
            continue
        table = SQLModel.metadata.tables[table_name]
        record_id = identity["record_id"]
        row = session.execute(
            sa_select(table).where(table.c[identity["primary_key"]] == record_id)
        ).mappings().first()
        if row is None:
            findings.append(
                MaterializedIdentityMismatch(
                    "materialized_record_missing",
                    table_name,
                    record_id,
                    f"receipt-bound materialized row is missing: {table_name}:{record_id}",
                )
            )
            continue
        if table_name in OWNER_SCOPED_TABLES and row.get("source") != owner:
            findings.append(
                MaterializedIdentityMismatch(
                    "materialized_record_owner_mismatch",
                    table_name,
                    record_id,
                    f"materialized row owner mismatch: {table_name}:{record_id}",
                )
            )
        actual_digest = _row_content_digest(table_name, row)
        if actual_digest != identity["content_sha256"]:
            findings.append(
                MaterializedIdentityMismatch(
                    "materialized_record_content_mismatch",
                    table_name,
                    record_id,
                    f"materialized row content drift: {table_name}:{record_id}",
                )
            )
        expected_by_table.setdefault(table_name, set()).add(record_id)

    for table_name, domain in OWNER_SCOPED_TABLES.items():
        if domain not in current_domains:
            continue
        table = SQLModel.metadata.tables[table_name]
        primary_key = next(iter(table.primary_key.columns)).name
        actual_ids = {
            str(row[0])
            for row in session.execute(
                sa_select(table.c[primary_key]).where(table.c.source == owner)
            ).all()
        }
        expected_ids = expected_by_table.get(table_name, set())
        for record_id in sorted(actual_ids - expected_ids):
            findings.append(
                MaterializedIdentityMismatch(
                    "materialized_record_extra",
                    table_name,
                    record_id,
                    f"owner-scoped row is not declared by current receipt: "
                    f"{table_name}:{record_id}",
                )
            )

    expected_positions: dict[str, set[str]] = {}
    for identity in normalized:
        if identity["table"] == "positions":
            expected_positions.setdefault(identity["scope_id"], set()).add(
                identity["record_id"]
            )
    position_table = SQLModel.metadata.tables["positions"]
    for snapshot_id, expected_ids in expected_positions.items():
        actual_ids = {
            str(row[0])
            for row in session.execute(
                sa_select(position_table.c.position_id).where(
                    position_table.c.snapshot_id == snapshot_id
                )
            ).all()
        }
        for record_id in sorted(actual_ids - expected_ids):
            findings.append(
                MaterializedIdentityMismatch(
                    "materialized_record_extra",
                    "positions",
                    record_id,
                    f"snapshot row is not declared by receipt: positions:{record_id}",
                )
            )
    return findings
