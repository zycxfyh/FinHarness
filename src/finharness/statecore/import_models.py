"""Typed provenance records for production capital imports."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field

from finharness.statecore.model_base import StateCoreBase, json_dict_column

IMPORT_COVERAGE_MODES: tuple[str, ...] = ("full", "delta")
IMPORT_MATERIALIZATION_STATUSES: tuple[str, ...] = ("materialized",)


class ImportBatch(StateCoreBase, table=True):
    """Stable identity and source evidence for one content-addressed import."""

    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "coverage_mode IN ('full', 'delta')",
            name="ck_import_batches_coverage_mode_closed",
        ),
        UniqueConstraint(
            "source_kind",
            "source_id",
            "source_sha256",
            "adapter_version",
            "import_schema_version",
            name="uq_import_batches_content_contract",
        ),
    )

    batch_id: str = Field(primary_key=True)
    source_kind: str = Field(index=True)
    source_id: str
    coverage_mode: str
    source_sha256: str = Field(index=True)
    source_artifact_id: str
    adapter_version: str
    import_schema_version: str
    record_counts: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())


class ReceiptManifest(StateCoreBase, table=True):
    """Binding between immutable import evidence and committed queryable state."""

    __tablename__ = "receipt_manifests"
    __table_args__ = (
        CheckConstraint(
            "materialization_status = 'materialized'",
            name="ck_receipt_manifests_materialized_only",
        ),
        UniqueConstraint("batch_id", name="uq_receipt_manifests_batch_id"),
        UniqueConstraint("receipt_id", name="uq_receipt_manifests_receipt_id"),
    )

    manifest_id: str = Field(primary_key=True)
    batch_id: str = Field(foreign_key="import_batches.batch_id", index=True)
    receipt_id: str
    receipt_ref: str
    receipt_sha256: str
    receipt_artifact_id: str
    source_artifact_id: str
    snapshot_id: str
    materialization_status: str
    record_counts: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    materialized_at_utc: str
