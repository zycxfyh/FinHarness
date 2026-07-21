"""Receipt-bound positive proof for capital-import materialized record identities."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select as sa_select
from sqlmodel import Session, SQLModel

MATERIALIZED_RECORD_IDENTITIES_FIELD = "materialized_record_identities"

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


class MaterializedRecordIdentityError(RuntimeError):
    """Raised when receipt-bound materialized identity proof is malformed."""


@dataclass(frozen=True)
class MaterializedIdentityMismatch:
    code: str
    table: str
    record_id: str
    message: str


def _identity_sort_key(item: Mapping[str, str]) -> tuple[str, str, str]:
    return (item["table"], item["record_id"], item.get("scope_id", ""))


def materialized_record_identity(record: Any) -> dict[str, str] | None:
    """Return one deterministic table/primary-key identity for a materialized row."""
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
    }
    if table.name == "positions":
        identity["scope_id"] = str(getattr(record, "snapshot_id", "") or "")
    return identity


def materialized_record_identities(records: Iterable[Any]) -> list[dict[str, str]]:
    """Freeze the exact non-tombstone queryable rows one import claims to materialize."""
    identities = [
        identity
        for record in records
        if (identity := materialized_record_identity(record)) is not None
    ]
    identities.sort(key=_identity_sort_key)
    keys = {(item["table"], item["record_id"]) for item in identities}
    if len(keys) != len(identities):
        raise MaterializedRecordIdentityError(
            "materialized record identity proof contains duplicate table identities"
        )
    return identities


def normalize_materialized_record_identities(
    raw: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, str]]:
    """Validate and normalize immutable receipt identity proof."""
    if raw is None:
        raise MaterializedRecordIdentityError(
            "receipt has no materialized record identity proof"
        )
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
        if table_name == "positions" and not scope_id:
            raise MaterializedRecordIdentityError(
                "position materialized identity requires snapshot scope_id"
            )
        normalized.append(entry)
    normalized.sort(key=_identity_sort_key)
    keys = {(item["table"], item["record_id"]) for item in normalized}
    if len(keys) != len(normalized):
        raise MaterializedRecordIdentityError(
            "materialized record identity proof contains duplicate table identities"
        )
    return normalized


def audit_materialized_record_identities(
    session: Session,
    *,
    source_kind: str,
    source_id: str,
    expected: Sequence[Mapping[str, Any]],
    current_domains: set[str],
) -> list[MaterializedIdentityMismatch]:
    """Compare receipt-bound identities with the queryable mirror without guessing."""
    normalized = normalize_materialized_record_identities(expected)
    owner = f"{source_kind}::{source_id}"
    findings: list[MaterializedIdentityMismatch] = []
    expected_by_table: dict[str, set[str]] = {}
    for identity in normalized:
        table_name = identity["table"]
        domain = identity["domain"]
        if table_name in OWNER_SCOPED_TABLES and domain not in current_domains:
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
            expected_positions.setdefault(identity["scope_id"], set()).add(identity["record_id"])
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
