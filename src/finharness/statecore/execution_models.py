"""Canonical Execution Kernel — StateCore models for the execution lifecycle.

The execution kernel models a full live-shaped execution system:
order drafting, pre-trade checking, approval, order staging, broker
submission, execution reporting, position tracking, and reconciliation.

This is a *positive* execution model — not a "not live" protection
layer. LIVE is a legal environment. BrokerConnection is a legal entity.
Submit is a legal command.

The hard engineering boundary:
    Only SimulatedBrokerAdapter is registered.
    No real external broker, credential, account funding, or venue
    connectivity exists.
"""
# ruff: noqa: UP042


from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pydantic import field_validator
from sqlalchemy import CheckConstraint, Column, String
from sqlmodel import Field, SQLModel

from finharness.statecore.models import (
    STATE_CORE_SCHEMA_VERSION,
    json_list_column,
    money_column,
)

# ── Environment ──────────────────────────────────────────────────────────────


class ExecutionEnvironment(str, Enum):
    PAPER = "paper"
    LIVE = "live"


EXECUTION_ENVIRONMENTS: tuple[str, ...] = ("paper", "live")


# ── Order draft statuses ─────────────────────────────────────────────────────

ORDER_DRAFT_STATUSES: tuple[str, ...] = (
    "draft",
    "pretrade_check_pending",
    "pretrade_check_passed",
    "pretrade_check_blocked",
    "approval_pending",
    "approved",
    "rejected",
    "staged",
    "cancelled",
)

ORDER_SIDES: tuple[str, ...] = ("buy", "sell")
ORDER_TYPES: tuple[str, ...] = ("market", "limit", "stop", "stop_limit")
ORDER_TIFS: tuple[str, ...] = ("day", "gtc", "ioc", "fok")

# ── Execution order statuses ─────────────────────────────────────────────────

EXECUTION_ORDER_STATUSES: tuple[str, ...] = (
    "staged",
    "submit_pending",
    "submitted",
    "acknowledged",
    "partial_fill",
    "filled",
    "rejected",
    "cancelled",
    "expired",
)

# ── Execution report types ───────────────────────────────────────────────────

EXECUTION_REPORT_TYPES: tuple[str, ...] = (
    "submit_ack",
    "cancel_ack",
    "fill",
    "partial_fill",
    "reject",
    "cancel_reject",
    "simulated_submit_ack",
    "simulated_fill",
    "simulated_reject",
)

FILL_STATUSES: tuple[str, ...] = (
    "none",
    "partial",
    "filled",
    "rejected",
    "cancelled",
)

# ── Pre-trade check statuses ─────────────────────────────────────────────────

PRETRADE_CHECK_STATUSES: tuple[str, ...] = ("pass", "warn", "block", "pending")

APPROVAL_DECISIONS: tuple[str, ...] = ("approved", "rejected", "deferred")

RECONCILIATION_STATUSES: tuple[str, ...] = ("matched", "unmatched", "pending")


# ── Utility ──────────────────────────────────────────────────────────────────


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


# ── Models ───────────────────────────────────────────────────────────────────


class BrokerConnection(SQLModel, table=True):
    """A broker adapter connection — paper or live.

    The connection records intent, not capability. A live connection
    with adapter_kind="simulated" is a live-shaped testing substrate,
    not a real external broker.
    """

    __tablename__ = "broker_connections"
    __table_args__ = (
        CheckConstraint(
            "environment IN (" + ", ".join(f"'{e}'" for e in EXECUTION_ENVIRONMENTS) + ")",
            name="ck_broker_connections_environment",
        ),
    )

    broker_connection_id: str = Field(primary_key=True)
    environment: str = Field(
        default="paper",
        sa_column=Column(String, nullable=False),
    )
    broker_name: str
    adapter_kind: str
    enabled: bool = True
    network_enabled: bool = False
    credential_ref: str | None = None
    schema_version: str = STATE_CORE_SCHEMA_VERSION
    created_at_utc: str = Field(default_factory=_utc_now)

    @field_validator("network_enabled")
    @classmethod
    def simulated_is_not_network(cls, v: bool) -> bool:
        """Simulated adapters never have network enabled."""
        return v


class ExecutionAccount(SQLModel, table=True):
    """An account bound to a broker connection for execution.

    A live account with funded=False is a valid testing account.
    """

    __tablename__ = "execution_accounts"
    __table_args__ = (
        CheckConstraint(
            "environment IN (" + ", ".join(f"'{e}'" for e in EXECUTION_ENVIRONMENTS) + ")",
            name="ck_execution_accounts_environment",
        ),
    )

    execution_account_id: str = Field(primary_key=True)
    broker_connection_id: str = Field(foreign_key="broker_connections.broker_connection_id")
    environment: str = Field(
        default="paper",
        sa_column=Column(String, nullable=False),
    )
    account_label: str
    base_currency: str = "USD"
    funded: bool = False
    external_account_ref: str | None = None
    schema_version: str = STATE_CORE_SCHEMA_VERSION
    created_at_utc: str = Field(default_factory=_utc_now)


class OrderDraft(SQLModel, table=True):
    """A draft order — the canonical starting point for execution.

    It carries side, quantity, order type,
    and an explicit execution account. It is the first artifact in the
    positive execution lifecycle.
    """

    __tablename__ = "order_drafts"
    __table_args__ = (
        CheckConstraint(
            "environment IN (" + ", ".join(f"'{e}'" for e in EXECUTION_ENVIRONMENTS) + ")",
            name="ck_order_drafts_environment",
        ),
        CheckConstraint(
            "side IN (" + ", ".join(f"'{s}'" for s in ORDER_SIDES) + ")",
            name="ck_order_drafts_side",
        ),
        CheckConstraint(
            "order_type IN (" + ", ".join(f"'{t}'" for t in ORDER_TYPES) + ")",
            name="ck_order_drafts_order_type",
        ),
        CheckConstraint(
            "time_in_force IN (" + ", ".join(f"'{t}'" for t in ORDER_TIFS) + ")",
            name="ck_order_drafts_tif",
        ),
        CheckConstraint(
            "draft_status IN (" + ", ".join(f"'{s}'" for s in ORDER_DRAFT_STATUSES) + ")",
            name="ck_order_drafts_status",
        ),
        CheckConstraint("quantity > 0", name="ck_order_drafts_quantity_positive"),
    )

    order_draft_id: str = Field(primary_key=True)
    proposal_id: str | None = None
    environment: str = Field(
        default="paper",
        sa_column=Column(String, nullable=False),
    )
    execution_account_id: str = Field(
        foreign_key="execution_accounts.execution_account_id", index=True
    )
    instrument_ref: str
    symbol: str
    side: str
    order_type: str
    quantity: Decimal = Field(sa_column=money_column())
    limit_price: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    stop_price: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    time_in_force: str = "day"
    currency: str = "USD"
    rationale: str
    source_kind: str = ""
    source_ref: str = ""
    draft_status: str = "draft"
    validation_findings: list[dict[str, object]] | None = Field(
        default=None, sa_column=json_list_column()
    )
    schema_version: str = STATE_CORE_SCHEMA_VERSION
    receipt_ref: str | None = None
    created_at_utc: str = Field(default_factory=_utc_now)

    @field_validator("symbol", "instrument_ref", "rationale")
    @classmethod
    def require_context(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("order draft requires symbol, instrument_ref, and rationale")
        return v


class PreTradeCheck(SQLModel, table=True):
    """A pre-trade check run against an order draft.

    Records findings, required approval level, and overall status.
    It records deterministic pre-trade findings.
    """

    __tablename__ = "pretrade_checks"
    __table_args__ = (
        CheckConstraint(
            "check_status IN (" + ", ".join(f"'{s}'" for s in PRETRADE_CHECK_STATUSES) + ")",
            name="ck_pretrade_checks_status",
        ),
    )

    pretrade_check_id: str = Field(primary_key=True)
    order_draft_id: str = Field(foreign_key="order_drafts.order_draft_id", index=True)
    check_status: str = "pending"
    findings_json: str = "[]"
    required_approval_level: str = "human"
    schema_version: str = STATE_CORE_SCHEMA_VERSION
    receipt_ref: str | None = None
    created_at_utc: str = Field(default_factory=_utc_now)


class ApprovalRecord(SQLModel, table=True):
    """A human approval decision on an order draft.

    It records the admission decision used by the current execution path.
    """

    __tablename__ = "approval_records"
    __table_args__ = (
        CheckConstraint(
            "decision IN (" + ", ".join(f"'{d}'" for d in APPROVAL_DECISIONS) + ")",
            name="ck_approval_records_decision",
        ),
    )

    approval_id: str = Field(primary_key=True)
    order_draft_id: str = Field(foreign_key="order_drafts.order_draft_id", index=True)
    decision: str
    reviewer_id: str
    rationale: str
    schema_version: str = STATE_CORE_SCHEMA_VERSION
    receipt_ref: str | None = None
    created_at_utc: str = Field(default_factory=_utc_now)

    @field_validator("reviewer_id", "rationale")
    @classmethod
    def require_reviewer_context(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("approval requires reviewer_id and rationale")
        return v


class ExecutionOrder(SQLModel, table=True):
    """A staged order ready for broker submission.

    The submission itself is a command, not a state field.
    The broker_order_ref is populated by the adapter after submission.
    """

    __tablename__ = "execution_orders"
    __table_args__ = (
        CheckConstraint(
            "environment IN (" + ", ".join(f"'{e}'" for e in EXECUTION_ENVIRONMENTS) + ")",
            name="ck_execution_orders_environment",
        ),
        CheckConstraint(
            "execution_status IN ("
            + ", ".join(f"'{s}'" for s in EXECUTION_ORDER_STATUSES)
            + ")",
            name="ck_execution_orders_status",
        ),
    )

    execution_order_id: str = Field(primary_key=True)
    order_draft_id: str = Field(foreign_key="order_drafts.order_draft_id", index=True)
    broker_connection_id: str = Field(
        foreign_key="broker_connections.broker_connection_id", index=True
    )
    environment: str = Field(
        default="paper",
        sa_column=Column(String, nullable=False),
    )
    broker_order_ref: str | None = None
    execution_status: str = "staged"
    submitted_at_utc: str | None = None
    schema_version: str = STATE_CORE_SCHEMA_VERSION
    receipt_ref: str | None = None
    created_at_utc: str = Field(default_factory=_utc_now)


class ExecutionReport(SQLModel, table=True):
    """A broker response: fill, reject, or simulated acknowledgement.

    For simulated adapters, this carries the simulated fill/reject
    result with no real external side effect.
    """

    __tablename__ = "execution_reports"
    __table_args__ = (
        CheckConstraint(
            "report_type IN ("
            + ", ".join(f"'{t}'" for t in EXECUTION_REPORT_TYPES)
            + ")",
            name="ck_execution_reports_type",
        ),
        CheckConstraint(
            "fill_status IN (" + ", ".join(f"'{s}'" for s in FILL_STATUSES) + ")",
            name="ck_execution_reports_fill_status",
        ),
    )

    execution_report_id: str = Field(primary_key=True)
    execution_order_id: str = Field(
        foreign_key="execution_orders.execution_order_id", index=True
    )
    report_type: str
    fill_status: str = "none"
    filled_quantity: Decimal = Field(default=Decimal("0"), sa_column=money_column())
    average_fill_price: Decimal | None = Field(
        default=None, sa_column=money_column(nullable=True)
    )
    broker_event_ref: str | None = None
    schema_version: str = STATE_CORE_SCHEMA_VERSION
    receipt_ref: str | None = None
    created_at_utc: str = Field(default_factory=_utc_now)


class PositionDelta(SQLModel, table=True):
    """A change in paper or live position resulting from an execution report."""

    __tablename__ = "position_deltas"

    position_delta_id: str = Field(primary_key=True)
    execution_report_id: str = Field(
        foreign_key="execution_reports.execution_report_id", index=True
    )
    execution_account_id: str = Field(
        foreign_key="execution_accounts.execution_account_id", index=True
    )
    symbol: str
    delta_quantity: Decimal = Field(sa_column=money_column())
    post_execution_quantity: Decimal = Field(sa_column=money_column())
    schema_version: str = STATE_CORE_SCHEMA_VERSION
    receipt_ref: str | None = None
    created_at_utc: str = Field(default_factory=_utc_now)

    @field_validator("symbol")
    @classmethod
    def require_symbol(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("position delta requires symbol")
        return v


class ReconciliationReport(SQLModel, table=True):
    """A comparison of expected vs actual positions after execution."""

    __tablename__ = "reconciliation_reports"
    __table_args__ = (
        CheckConstraint(
            "reconciliation_status IN ("
            + ", ".join(f"'{s}'" for s in RECONCILIATION_STATUSES)
            + ")",
            name="ck_reconciliation_reports_status",
        ),
    )

    reconciliation_id: str = Field(primary_key=True)
    execution_account_id: str = Field(
        foreign_key="execution_accounts.execution_account_id", index=True
    )
    reconciliation_status: str = "pending"
    expected_positions_json: str = "[]"
    actual_positions_json: str = "[]"
    discrepancies_json: str = "[]"
    schema_version: str = STATE_CORE_SCHEMA_VERSION
    receipt_ref: str | None = None
    created_at_utc: str = Field(default_factory=_utc_now)
