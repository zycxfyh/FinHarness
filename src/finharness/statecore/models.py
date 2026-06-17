"""SQLModel tables for the FinHarness state core.

The state core is queryable state, not evidence. Receipt files remain the
source of truth; these tables only store state snapshots, read indexes, and
governed proposals that never carry execution authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import field_validator
from sqlalchemy import JSON, CheckConstraint, Column, Index
from sqlmodel import Field, SQLModel

STATE_CORE_SCHEMA_VERSION = "finharness.state_core.v1"
AuthorityLevel = str
Decision = str


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def json_list_column() -> Any:
    return Column(JSON, nullable=False)


def json_dict_column() -> Any:
    return Column(JSON, nullable=False)


class StateCoreBase(SQLModel):
    """Common governance columns shared by state-core tables."""

    schema_version: str = STATE_CORE_SCHEMA_VERSION
    as_of_utc: str = Field(default_factory=utc_now_iso)
    authority_level: AuthorityLevel = "read_only"


class Account(StateCoreBase, table=True):
    __tablename__ = "accounts"

    account_id: str = Field(primary_key=True)
    kind: str
    venue: str
    display_name: str
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    created_at_utc: str = Field(default_factory=utc_now_iso)


class Snapshot(StateCoreBase, table=True):
    __tablename__ = "snapshots"
    __table_args__ = (Index("ix_snapshots_kind_as_of_utc", "kind", "as_of_utc"),)

    snapshot_id: str = Field(primary_key=True)
    kind: str = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class Position(StateCoreBase, table=True):
    __tablename__ = "positions"

    position_id: str = Field(primary_key=True)
    snapshot_id: str = Field(foreign_key="snapshots.snapshot_id", index=True)
    account_id: str = Field(foreign_key="accounts.account_id")
    symbol: str
    quantity: float
    market_value: float
    cost_basis: float | None = None
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class ReceiptIndex(StateCoreBase, table=True):
    """Read-only index for receipt files.

    The indexed file remains the source of truth. This table is only a lookup
    surface for cockpit/API reads.
    """

    __tablename__ = "receipt_index"

    receipt_id: str = Field(primary_key=True)
    kind: str
    path: str
    created_at_utc: str = Field(default_factory=utc_now_iso)
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class Proposal(StateCoreBase, table=True):
    __tablename__ = "proposals"
    __table_args__ = (
        CheckConstraint("execution_allowed = 0", name="ck_proposals_execution_allowed_false"),
    )

    proposal_id: str = Field(primary_key=True)
    kind: str
    claim: str
    evidence: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    assumptions: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    limitations: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    non_claims: list[str] = Field(default_factory=list, sa_column=json_list_column())
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    authority_level: AuthorityLevel = "needs_human_confirm"
    execution_allowed: bool = False
    receipt_ref: str | None = None
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("state-core proposals never carry execution authority")
        return False


class Attestation(StateCoreBase, table=True):
    __tablename__ = "attestations"

    attestation_id: str = Field(primary_key=True)
    proposal_id: str = Field(foreign_key="proposals.proposal_id")
    attester: str
    reason: str
    decision: Decision
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    authority_level: AuthorityLevel = "needs_human_confirm"
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("attester", "reason")
    @classmethod
    def require_written_human_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("attestation requires a named human and written reason")
        return value
