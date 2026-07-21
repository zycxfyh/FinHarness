"""Typed provenance records for production capital imports."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field

from finharness.statecore.model_base import (
    StateCoreBase,
    json_dict_column,
    json_list_column,
)

IMPORT_COVERAGE_MODES: tuple[str, ...] = ("full", "delta")
IMPORT_MATERIALIZATION_STATUSES: tuple[str, ...] = ("materialized",)
IMPORT_COMPLETENESS_STATUSES: tuple[str, ...] = (
    "complete",
    "partial",
    "blocked",
    "legacy_unknown",
)
CORPORATE_ACTION_STATUSES: tuple[str, ...] = ("not_applicable", "unsupported_gap")


class ImportBatch(StateCoreBase, table=True):
    """Stable identity and source evidence for one content-addressed import."""

    __tablename__ = "import_batches"
    __table_args__ = (
        CheckConstraint(
            "coverage_mode IN ('full', 'delta')",
            name="ck_import_batches_coverage_mode_closed",
        ),
        CheckConstraint(
            "completeness_status IN ('complete', 'partial', 'blocked', 'legacy_unknown')",
            name="ck_import_batches_completeness_status_closed",
        ),
        CheckConstraint(
            "corporate_action_status IN ('not_applicable', 'unsupported_gap')",
            name="ck_import_batches_corporate_action_status_closed",
        ),
        UniqueConstraint(
            "source_kind",
            "source_id",
            "source_sha256",
            "adapter_version",
            "import_schema_version",
            "contract_digest",
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
    contract_digest: str = ""
    record_counts: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    covered_domains: list[str] = Field(default_factory=list, sa_column=json_list_column())
    supersedes_batch_id: str | None = Field(default=None, index=True)
    correction_reason: str | None = None
    corporate_action_status: str = "unsupported_gap"
    corporate_action_gaps: list[str] = Field(default_factory=list, sa_column=json_list_column())
    completeness_status: str = "complete"
    time_semantics: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    findings: list[dict[str, Any]] = Field(default_factory=list, sa_column=json_list_column())


class ImportDomainHead(StateCoreBase, table=True):
    """Atomic current-batch pointer for one source-owned import domain."""

    __tablename__ = "import_domain_heads"
    __table_args__ = (
        UniqueConstraint(
            "source_kind",
            "source_id",
            "domain",
            name="uq_import_domain_heads_source_domain",
        ),
    )

    domain_head_id: str = Field(primary_key=True)
    source_kind: str = Field(index=True)
    source_id: str
    domain: str = Field(index=True)
    batch_id: str = Field(foreign_key="import_batches.batch_id", index=True)
    manifest_id: str = Field(foreign_key="receipt_manifests.manifest_id", index=True)
    materialized_at_utc: str


class ImportTombstone(StateCoreBase, table=True):
    """Append-only evidence that one source-owned row disappeared or was deleted."""

    __tablename__ = "import_tombstones"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "record_type",
            "record_id",
            name="uq_import_tombstones_batch_record",
        ),
    )

    tombstone_id: str = Field(primary_key=True)
    batch_id: str = Field(foreign_key="import_batches.batch_id", index=True)
    source_kind: str = Field(index=True)
    record_type: str
    record_id: str
    reason: str
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


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
