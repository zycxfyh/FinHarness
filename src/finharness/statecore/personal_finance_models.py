"""Personal-finance models extracted from the shared models module.

These models represent personal finance facts — accounts, positions,
liabilities, goals, cashflows, taxes, insurance, and document references.
They are low-coupling: they depend on StateCoreBase/SourcedStateCoreBase
but not on proposal, execution, review, or agentic workflow models.

Extracted from statecore/models.py per STATECORE-01 / ENG-DEBT-0006.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlmodel import Field

from finharness.statecore.model_base import (
    SourcedStateCoreBase,
    StateCoreBase,
    json_dict_column,
    json_list_column,
    money_column,
    utc_now_iso,
)


class Account(StateCoreBase, table=True):
    __tablename__ = "accounts"

    account_id: str = Field(primary_key=True)
    canonical_account_id: str | None = Field(
        default=None, foreign_key="account_identities.canonical_account_id", index=True
    )
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
    __table_args__ = (
        CheckConstraint(
            "valuation_status IN ('valued', 'valued_converted', 'unpriced', "
            "'fx_missing', 'stale', 'unknown_legacy')",
            name="ck_positions_valuation_status",
        ),
    )

    position_id: str = Field(primary_key=True)
    snapshot_id: str = Field(foreign_key="snapshots.snapshot_id", index=True)
    account_id: str = Field(foreign_key="accounts.account_id")
    instrument_id: str | None = Field(
        default=None, foreign_key="instrument_identities.instrument_id", index=True
    )
    symbol: str
    quantity: Decimal = Field(sa_column=money_column())
    market_value: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    cost_basis: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    valuation_currency: str | None = Field(default=None, index=True)
    unit_price: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    price_currency: str | None = None
    valued_at_utc: str | None = None
    price_source_ref: str | None = None
    fx_rate: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    fx_as_of_utc: str | None = None
    fx_source_ref: str | None = None
    valuation_status: str = Field(default="unknown_legacy", index=True)
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class AccountIdentity(StateCoreBase, table=True):
    """Canonical account identity; display names are deliberately non-identifying."""

    __tablename__ = "account_identities"
    __table_args__ = (
        UniqueConstraint(
            "source_namespace",
            "source_native_id",
            "identity_version",
            name="uq_account_identity_source_native_version",
        ),
    )

    canonical_account_id: str = Field(primary_key=True)
    source_namespace: str = Field(index=True)
    source_native_id: str
    identity_version: str = "finharness.account_identity.v0"
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class InstrumentIdentity(StateCoreBase, table=True):
    """Small, explicit identity key; this is not a full security master."""

    __tablename__ = "instrument_identities"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "instrument_type",
            "venue",
            "quote_currency",
            "identity_version",
            name="uq_instrument_identity_components_version",
        ),
    )

    instrument_id: str = Field(primary_key=True)
    symbol: str = Field(index=True)
    instrument_type: str
    venue: str
    quote_currency: str
    identity_version: str = "finharness.instrument_identity.v0"
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())


class IdentityAlias(StateCoreBase, table=True):
    """Versioned evidence that a provider-native alias maps to a canonical ID."""

    __tablename__ = "identity_aliases"
    __table_args__ = (
        UniqueConstraint(
            "identity_kind",
            "provider_namespace",
            "provider_alias",
            "mapping_version",
            name="uq_identity_alias_mapping_version",
        ),
    )

    alias_id: str = Field(primary_key=True)
    identity_kind: str = Field(index=True)
    provider_namespace: str
    provider_alias: str
    canonical_id: str = Field(index=True)
    mapping_version: str = "finharness.identity_alias.v0"
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
