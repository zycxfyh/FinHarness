"""Typed provenance records for production capital imports."""

from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field

from finharness.statecore.model_base import (
    StateCoreBase,
    json_dict_column,
    json_list_column,
    utc_now_iso,
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


class CapitalImportSource(StateCoreBase, table=True):
    """Stable logical identity for one external capital source."""

    __tablename__ = "capital_import_sources"

    source_id: str = Field(primary_key=True)
    source_kind: str = Field(index=True)
    display_name: str = ""
    identity_version: str = "finharness.capital_import_source.v1"
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    created_at_utc: str = Field(default_factory=utc_now_iso)


class CapitalImportSourceAlias(StateCoreBase, table=True):
    """Discovery alias that never owns canonical source identity."""

    __tablename__ = "capital_import_source_aliases"
    __table_args__ = (
        UniqueConstraint(
            "alias_kind",
            "alias_value",
            name="uq_capital_import_source_alias",
        ),
    )

    alias_id: str = Field(primary_key=True)
    source_id: str = Field(foreign_key="capital_import_sources.source_id", index=True)
    alias_kind: str = Field(index=True)
    alias_value: str
    created_at_utc: str = Field(default_factory=utc_now_iso)


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
            "coverage_mode",
            "supersedes_batch_id",
            name="uq_import_batches_content_contract",
        ),
    )

    batch_id: str = Field(primary_key=True)
    source_kind: str = Field(index=True)
    source_id: str
    stable_source_id: str | None = Field(
        default=None,
        foreign_key="capital_import_sources.source_id",
        index=True,
    )
    coverage_mode: str
    source_sha256: str = Field(index=True)
    source_artifact_id: str
    projection_artifact_id: str | None = None
    projection_sha256: str | None = Field(default=None, index=True)
    projection_schema_version: str | None = None
    projection_payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=json_dict_column(),
    )
    effective_at_utc: str | None = Field(default=None, index=True)
    observed_at_utc: str | None = Field(default=None, index=True)
    recorded_at_utc: str | None = Field(default=None, index=True)
    adapter_version: str
    import_schema_version: str
    record_counts: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    covered_domains: list[str] = Field(default_factory=list, sa_column=json_list_column())
    supersedes_batch_id: str | None = Field(default=None, index=True)
    correction_reason: str | None = None
    corporate_action_status: str = "unsupported_gap"
    corporate_action_gaps: list[str] = Field(default_factory=list, sa_column=json_list_column())
    completeness_status: str = "complete"
    time_semantics: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    findings: list[dict[str, Any]] = Field(default_factory=list, sa_column=json_list_column())


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
    stable_source_id: str | None = Field(default=None, index=True)
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
