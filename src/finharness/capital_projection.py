"""Immutable normalized projections for capital import batches."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlmodel import SQLModel

from finharness.artifact_store import ArtifactDescriptor, ArtifactStore

CAPITAL_PROJECTION_SCHEMA = "finharness.capital_import_projection"
CAPITAL_PROJECTION_SCHEMA_VERSION = "finharness.capital_import_projection.v1"


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def canonical_projection_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            _canonical(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _record_payload(
    record: SQLModel,
    *,
    stable_source_id: str,
    observed_at_utc: str,
) -> dict[str, Any]:
    record_type = type(record).__name__
    payload = _canonical(record.model_dump(mode="python"))
    if isinstance(payload, dict):
        payload["source_refs"] = [stable_source_id]
        if record_type == "Account":
            payload["created_at_utc"] = observed_at_utc
        if record_type in {"AccountIdentity", "InstrumentIdentity", "IdentityAlias"}:
            payload["as_of_utc"] = observed_at_utc
        if record_type == "Snapshot" and isinstance(payload.get("payload"), dict):
            payload["payload"] = {
                **payload["payload"],
                "source_ref": stable_source_id,
            }
    return {"record_type": record_type, "payload": payload}


def build_capital_projection(
    *,
    batch_id: str,
    stable_source_id: str,
    source_kind: str,
    coverage_mode: str,
    covered_domains: Sequence[str],
    time_semantics: dict[str, Any],
    records: Sequence[SQLModel],
) -> dict[str, Any]:
    observed_at_utc = str(time_semantics.get("observed_at_utc") or "")
    projected = [
        _record_payload(
            record,
            stable_source_id=stable_source_id,
            observed_at_utc=observed_at_utc,
        )
        for record in records
    ]
    projected.sort(
        key=lambda item: (
            str(item["record_type"]),
            json.dumps(item["payload"], sort_keys=True, default=str),
        )
    )
    return {
        "schema": CAPITAL_PROJECTION_SCHEMA_VERSION,
        "batch_id": batch_id,
        "stable_source_id": stable_source_id,
        "source_kind": source_kind,
        "coverage_mode": coverage_mode,
        "covered_domains": sorted(set(covered_domains)),
        "time_semantics": _canonical(time_semantics),
        "records": projected,
    }


def persist_capital_projection(
    *,
    artifact_store: ArtifactStore,
    projection: dict[str, Any],
    source_artifact_id: str,
    created_at_utc: str,
) -> ArtifactDescriptor:
    content = canonical_projection_bytes(projection)
    digest = hashlib.sha256(content).hexdigest()
    return artifact_store.put(
        artifact_id=f"capital_projection_{digest[:24]}",
        content=content,
        artifact_schema=CAPITAL_PROJECTION_SCHEMA,
        artifact_schema_version=CAPITAL_PROJECTION_SCHEMA_VERSION,
        media_type="application/json",
        owner_domain="capital_imports",
        created_at_utc=created_at_utc,
        source_refs=(source_artifact_id,),
        metadata={
            "batch_id": str(projection["batch_id"]),
            "stable_source_id": str(projection["stable_source_id"]),
        },
    )


def projection_sha256(projection: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_projection_bytes(projection)).hexdigest()
