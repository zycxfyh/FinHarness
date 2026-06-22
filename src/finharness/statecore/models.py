"""SQLModel tables for the FinHarness state core.

The state core is queryable state, not evidence. Receipt files remain the
source of truth; these tables only store state snapshots, read indexes, and
governed proposals that never carry execution authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import field_validator
from sqlalchemy import JSON, CheckConstraint, Column, Index, String
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator
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


class DecimalText(TypeDecorator[Decimal]):
    """Store ``Decimal`` exactly as TEXT.

    SQLite ``NUMERIC`` affinity round-trips decimals through float, which
    reintroduces the precision loss money columns must avoid. Storing the
    canonical string keeps amounts exact for personal-finance state.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value: object, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        # A pre-existing database may still have REAL/NUMERIC affinity on this
        # column, so SQLite can hand back a float/int. Normalise via str() (its
        # shortest round-trip repr) instead of Decimal(float), which would carry
        # binary noise into the value.
        return Decimal(str(value))


def money_column(*, nullable: bool = False) -> Any:
    """Column for an exact monetary/decimal amount."""
    return Column(DecimalText, nullable=nullable)


class StateCoreBase(SQLModel):
    """Common governance columns shared by state-core tables."""

    schema_version: str = STATE_CORE_SCHEMA_VERSION
    as_of_utc: str = Field(default_factory=utc_now_iso)
    authority_level: AuthorityLevel = "read_only"


class SourcedStateCoreBase(StateCoreBase):
    """State-core tables fully owned by the import source that produced them.

    ``source`` names the adapter/import (e.g. ``personal_finance_export``,
    ``beancount_ledger``) so a re-import can replace exactly its own rows instead
    of accumulating stale rows through upsert. See ``replace_source_records``.
    """

    source: str = Field(default="")


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
    quantity: Decimal = Field(sa_column=money_column())
    market_value: Decimal = Field(sa_column=money_column())
    cost_basis: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class Liability(SourcedStateCoreBase, table=True):
    __tablename__ = "liabilities"

    liability_id: str = Field(primary_key=True)
    name: str
    liability_type: str
    balance: Decimal = Field(sa_column=money_column())
    currency: str
    account_id: str | None = Field(default=None, foreign_key="accounts.account_id")
    interest_rate: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    due_date: str | None = None
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class FinancialGoal(SourcedStateCoreBase, table=True):
    __tablename__ = "financial_goals"

    goal_id: str = Field(primary_key=True)
    name: str
    target_amount: Decimal = Field(sa_column=money_column())
    current_amount: Decimal = Field(sa_column=money_column())
    currency: str
    target_date: str | None = None
    status: str = "active"
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class CashflowEvent(SourcedStateCoreBase, table=True):
    __tablename__ = "cashflow_events"

    cashflow_id: str = Field(primary_key=True)
    description: str
    amount: Decimal = Field(sa_column=money_column())
    currency: str
    event_date: str
    category: str
    account_id: str | None = Field(default=None, foreign_key="accounts.account_id")
    frequency: str | None = None
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class TaxEvent(SourcedStateCoreBase, table=True):
    __tablename__ = "tax_events"

    tax_event_id: str = Field(primary_key=True)
    event_type: str
    jurisdiction: str
    due_date: str
    estimated_amount: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    currency: str | None = None
    status: str = "planned"
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class InsurancePolicy(SourcedStateCoreBase, table=True):
    __tablename__ = "insurance_policies"

    policy_id: str = Field(primary_key=True)
    policy_type: str
    provider: str
    coverage_amount: Decimal = Field(sa_column=money_column())
    premium_amount: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    currency: str
    renewal_date: str | None = None
    status: str = "active"
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class DocumentRef(SourcedStateCoreBase, table=True):
    __tablename__ = "document_refs"

    document_id: str = Field(primary_key=True)
    document_type: str
    title: str
    path: str
    related_object_id: str | None = None
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


REVIEW_EVENT_KINDS: tuple[str, ...] = ("annotation", "archive", "reopen", "compare_mark")


class ReviewEvent(StateCoreBase, table=True):
    """Append-only ledger of human review interactions on a governed proposal.

    Additive to (not a replacement for) Attestation: attestation stays the decision of
    record (approve/reject); ReviewEvent records annotation / archive / reopen /
    compare_mark. Never carries execution authority. ``content_hash`` is for
    integrity/replay only — it is NOT an idempotency key, so a repeated human annotation
    is a new event, not a no-op.
    """

    __tablename__ = "review_events"
    __table_args__ = (
        CheckConstraint(
            "execution_allowed = 0", name="ck_review_events_execution_allowed_false"
        ),
    )

    review_event_id: str = Field(primary_key=True)
    proposal_id: str = Field(foreign_key="proposals.proposal_id")
    kind: str
    attester: str
    reason: str
    text: str | None = None
    attestation_ref: str | None = None
    compare_with: str | None = None
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    content_hash: str = ""
    authority_level: AuthorityLevel = "needs_human_confirm"
    execution_allowed: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("kind")
    @classmethod
    def require_known_kind(cls, value: str) -> str:
        if value not in REVIEW_EVENT_KINDS:
            raise ValueError(f"review event kind must be one of {REVIEW_EVENT_KINDS}")
        return value

    @field_validator("attester", "reason")
    @classmethod
    def require_written_human_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("review event requires a named human and written reason")
        return value

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("review events never carry execution authority")
        return False
