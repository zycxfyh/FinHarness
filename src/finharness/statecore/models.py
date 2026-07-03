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
ACTION_INTENT_TYPES: tuple[str, ...] = (
    "reduce_exposure",
    "increase_exposure",
    "rebalance",
    "raise_cash",
    "defer_action",
    "hedge_review",
    "watchlist",
    "request_more_evidence",
)
ACTION_INTENT_NEXT_STEPS: tuple[str, ...] = (
    "action_preflight",
    "simulation",
    "human_review",
    "discard",
)
ACTION_INTENT_AUTHORS: tuple[str, ...] = ("agent", "human", "system")
ACTION_INTENT_SIMULATION_SCENARIO_MODES: tuple[str, ...] = (
    "descriptive_v0",
    "risk_posture_v0",
    "exposure_context_v0",
)
ACTION_INTENT_SIMULATION_STATUSES: tuple[str, ...] = (
    "complete",
    "incomplete",
    "blocked",
)
CAPITAL_MANDATE_STATUSES: tuple[str, ...] = ("active", "superseded")
CAPITAL_MANDATE_AUTONOMY_LEVELS: tuple[str, ...] = (
    "L0_read_only",
    "L1_candidate_only",
    "L2_human_confirmed_apply",
    "L3_bounded_delegation_candidate",
)
AGENT_AUTHORITY_GRANT_STATUSES: tuple[str, ...] = ("active", "revoked", "suspended")
TRADE_PLAN_CANDIDATE_DIRECTIONS: tuple[str, ...] = (
    "reduce",
    "increase",
    "rebalance",
    "hedge_review",
    "raise_cash",
    "defer",
    "watchlist",
    "request_more_evidence",
)
TRADE_PLAN_CANDIDATE_STATUSES: tuple[str, ...] = (
    "draft_candidate",
    "needs_authority_contract",
    "blocked_by_validation",
)
TRADE_PLAN_REVIEW_GATE_DECISIONS: tuple[str, ...] = (
    "allow_order_ticket_candidate_staging",
    "deny_order_ticket_candidate_staging",
)
TRADE_PLAN_REVIEW_GATE_REVIEWER_TYPES: tuple[str, ...] = ("human",)


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
    # Minimal decision forcing gate (P4). Empty for ungoverned/legacy rows; governed
    # proposals created via create_governed_proposal must carry the four required fields
    # (see finharness.statecore.decision_scaffold).
    decision_scaffold: dict[str, Any] = Field(
        default_factory=dict, sa_column=json_dict_column()
    )
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


REVIEW_EVENT_KINDS: tuple[str, ...] = (
    "annotation",
    "archive",
    "reopen",
    "compare_mark",
    "agent_review_note",
    "agent_scaffold_revision_apply_candidate",
)


class ReviewEvent(StateCoreBase, table=True):
    """Append-only ledger of human review interactions on a governed proposal.

    Additive to (not a replacement for) Attestation: attestation stays the decision of
    record (approve/reject); ReviewEvent records annotation / archive / reopen /
    compare_mark / agent_review_note / agent_scaffold_revision_apply_candidate.
    Never carries execution authority. ``content_hash`` is for integrity/replay only —
    it is NOT an idempotency key, so a repeated human annotation is a new event, not a
    no-op.
    """

    __tablename__ = "review_events"
    __table_args__ = (
        CheckConstraint(
            "execution_allowed = 0", name="ck_review_events_execution_allowed_false"
        ),
        # Closed set at the DB level: SQLModel table models skip field validators on
        # construction, so the kind enum must also be enforced where it is persisted.
        CheckConstraint(
            "kind IN (" + ", ".join(f"'{k}'" for k in REVIEW_EVENT_KINDS) + ")",
            name="ck_review_events_kind_closed",
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


class InvestmentPolicyStatement(StateCoreBase, table=True):
    """Personal Investment Policy Statement (north star L3 / 投资政策声明).

    The IPS turns the user's goals, constraints, and risk boundaries into a
    readable, versioned policy object. The numeric policy thresholds personalize
    the L4 allocation detectors (they override the default ``ObservationThresholds``
    via ``finharness.ips.thresholds_from_ips``); the declarative fields
    (allowed asset classes, restricted actions) are carried for review and agent
    context. An IPS is policy, never execution authority.

    Percent fields are stored as exact decimal fractions (``0.40`` == 40%);
    ``liquidity_floor_months`` is a decimal number of months of cash runway.
    """

    __tablename__ = "investment_policy_statements"
    __table_args__ = (
        CheckConstraint("execution_allowed = 0", name="ck_ips_execution_allowed_false"),
    )

    ips_id: str = Field(primary_key=True)
    status: str = "active"  # active | superseded
    base_currency: str = "USD"
    # Numeric policy thresholds consumed by the L4 detectors.
    liquidity_floor_months: Decimal = Field(sa_column=money_column())
    max_single_holding_pct: Decimal = Field(sa_column=money_column())
    cash_overweight_pct: Decimal | None = Field(default=None, sa_column=money_column(nullable=True))
    high_interest_rate_pct: Decimal | None = Field(
        default=None, sa_column=money_column(nullable=True)
    )
    # Declarative policy carried for review / agent context (not yet auto-enforced).
    allowed_asset_classes: list[str] = Field(default_factory=list, sa_column=json_list_column())
    restricted_actions: list[str] = Field(default_factory=list, sa_column=json_list_column())
    review_cadence: str = ""
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_ref: str | None = None
    authority_level: AuthorityLevel = "read_only"
    execution_allowed: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("an investment policy statement never carries execution authority")
        return False


class CapitalMandate(StateCoreBase, table=True):
    """Human-attested policy domain for future delegated capital authority.

    A ``CapitalMandate`` sits above an IPS. It captures the user's profile,
    objectives, risk boundaries, allowed assets/actions, limits, kill switches,
    review cadence, and explicit human attestation that future authority objects
    may reference. It is not an authority grant, order ticket, broker
    instruction, or execution authorization.
    """

    __tablename__ = "capital_mandates"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{status}'" for status in CAPITAL_MANDATE_STATUSES) + ")",
            name="ck_capital_mandates_status_closed",
        ),
        CheckConstraint(
            "autonomy_level IN ("
            + ", ".join(f"'{level}'" for level in CAPITAL_MANDATE_AUTONOMY_LEVELS)
            + ")",
            name="ck_capital_mandates_autonomy_level_closed",
        ),
        CheckConstraint(
            "explicit_confirmation = 1",
            name="ck_capital_mandates_explicit_confirmation_true",
        ),
        CheckConstraint(
            "execution_allowed = 0",
            name="ck_capital_mandates_execution_allowed_false",
        ),
        CheckConstraint(
            "authority_transition = 0",
            name="ck_capital_mandates_authority_transition_false",
        ),
    )

    capital_mandate_id: str = Field(primary_key=True)
    status: str = "active"
    source_ips_id: str | None = Field(
        default=None,
        foreign_key="investment_policy_statements.ips_id",
        index=True,
    )
    profile_snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    investment_objectives: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=json_dict_column(),
    )
    risk_profile: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    allowed_asset_classes: list[str] = Field(default_factory=list, sa_column=json_list_column())
    restricted_asset_classes: list[str] = Field(default_factory=list, sa_column=json_list_column())
    allowed_action_types: list[str] = Field(default_factory=list, sa_column=json_list_column())
    restricted_action_types: list[str] = Field(default_factory=list, sa_column=json_list_column())
    autonomy_level: str = "L1_candidate_only"
    limit_book: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    kill_switch_rules: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=json_list_column(),
    )
    review_cadence: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    human_attester: str
    human_reason: str
    explicit_confirmation: bool = True
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    non_claims: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_ref: str | None = None
    authority_level: AuthorityLevel = "human_attested_policy"
    execution_allowed: bool = False
    authority_transition: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("status")
    @classmethod
    def require_known_status(cls, value: str) -> str:
        if value not in CAPITAL_MANDATE_STATUSES:
            raise ValueError(f"capital mandate status must be one of {CAPITAL_MANDATE_STATUSES}")
        return value

    @field_validator("autonomy_level")
    @classmethod
    def require_known_autonomy_level(cls, value: str) -> str:
        if value not in CAPITAL_MANDATE_AUTONOMY_LEVELS:
            raise ValueError(
                "capital mandate autonomy_level must be one of "
                f"{CAPITAL_MANDATE_AUTONOMY_LEVELS}"
            )
        return value

    @field_validator("human_attester", "human_reason")
    @classmethod
    def require_human_attestation(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("capital mandate requires human attester and written reason")
        return value

    @field_validator("explicit_confirmation")
    @classmethod
    def require_explicit_confirmation(cls, value: bool) -> bool:
        if not value:
            raise ValueError("capital mandate requires explicit human confirmation")
        return True

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("capital mandates never carry execution authority")
        return False

    @field_validator("authority_transition")
    @classmethod
    def reject_authority_transition(cls, value: bool) -> bool:
        if value:
            raise ValueError("capital mandates never carry authority transitions")
        return False


class AgentAuthorityGrant(StateCoreBase, table=True):
    """Mandate-bound authority credential for an Agent.

    A grant gives an Agent a bounded authority credential under a currently
    active ``CapitalMandate``. It is dynamically validated at use time and never
    approves trade plans, submits orders, bypasses preflight, creates broker
    authority, or authorizes execution.
    """

    __tablename__ = "agent_authority_grants"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            + ", ".join(f"'{status}'" for status in AGENT_AUTHORITY_GRANT_STATUSES)
            + ")",
            name="ck_agent_authority_grants_status_closed",
        ),
        CheckConstraint(
            "execution_allowed = 0",
            name="ck_agent_authority_grants_execution_allowed_false",
        ),
        CheckConstraint(
            "authority_transition = 0",
            name="ck_agent_authority_grants_authority_transition_false",
        ),
    )

    agent_authority_grant_id: str = Field(primary_key=True)
    capital_mandate_id: str = Field(
        foreign_key="capital_mandates.capital_mandate_id",
        index=True,
    )
    agent_id: str = Field(index=True)
    agent_profile_name: str | None = None
    status: str = "active"
    grant_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    issued_by: str
    issued_reason: str
    issued_against_mandate_receipt_ref: str | None = None
    expires_at_utc: str | None = None
    revoked_at_utc: str | None = None
    revoked_reason: str | None = None
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    non_claims: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_ref: str | None = None
    authority_level: AuthorityLevel = "mandate_bound_authority_credential"
    execution_allowed: bool = False
    authority_transition: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("status")
    @classmethod
    def require_known_status(cls, value: str) -> str:
        if value not in AGENT_AUTHORITY_GRANT_STATUSES:
            raise ValueError(
                "agent authority grant status must be one of "
                f"{AGENT_AUTHORITY_GRANT_STATUSES}"
            )
        return value

    @field_validator("agent_id", "issued_by", "issued_reason")
    @classmethod
    def require_written_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agent authority grant requires agent, issuer, and reason")
        return value

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("agent authority grants never carry execution authority")
        return False

    @field_validator("authority_transition")
    @classmethod
    def reject_authority_transition(cls, value: bool) -> bool:
        if value:
            raise ValueError("agent authority grants never carry authority transitions")
        return False


class ActionIntent(StateCoreBase, table=True):
    """Candidate-only bridge from reviewed proposals to future capital actions.

    An ``ActionIntent`` says what capital action may be considered next. It is not
    an order ticket, broker instruction, simulation result, approval, or execution
    authorization.
    """

    __tablename__ = "action_intents"
    __table_args__ = (
        CheckConstraint("execution_allowed = 0", name="ck_action_intents_execution_allowed_false"),
        CheckConstraint(
            "authority_transition = 0",
            name="ck_action_intents_authority_transition_false",
        ),
        CheckConstraint(
            "action_type IN ("
            + ", ".join(f"'{action_type}'" for action_type in ACTION_INTENT_TYPES)
            + ")",
            name="ck_action_intents_type_closed",
        ),
        CheckConstraint(
            "expected_next_step IN ("
            + ", ".join(f"'{step}'" for step in ACTION_INTENT_NEXT_STEPS)
            + ")",
            name="ck_action_intents_next_step_closed",
        ),
        CheckConstraint(
            "created_by IN ("
            + ", ".join(f"'{author}'" for author in ACTION_INTENT_AUTHORS)
            + ")",
            name="ck_action_intents_created_by_closed",
        ),
    )

    action_intent_id: str = Field(primary_key=True)
    proposal_id: str = Field(foreign_key="proposals.proposal_id", index=True)
    source_proposal_receipt_ref: str
    source_revision_receipt_ref: str | None = None
    created_by: str
    active_profile: str | None = None
    action_type: str
    status: str = "candidate"
    target_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    intent_summary: str
    rationale: str
    constraints: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    trigger_context: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    required_preconditions: list[str] = Field(default_factory=list, sa_column=json_list_column())
    expected_next_step: str = "action_preflight"
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    non_claims: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_ref: str | None = None
    authority_level: AuthorityLevel = "needs_human_confirm"
    execution_allowed: bool = False
    authority_transition: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("action intents never carry execution authority")
        return False

    @field_validator("authority_transition")
    @classmethod
    def reject_authority_transition(cls, value: bool) -> bool:
        if value:
            raise ValueError("action intents never carry authority transitions")
        return False


class ActionIntentAuthorityBinding(StateCoreBase, table=True):
    """Receipt-backed authority admission result for an ActionIntentCandidate.

    A binding proves whether an author may admit an action intent into the next
    capital-action governance step. It is not preflight, approval, an order
    ticket, broker submission, or execution authorization.
    """

    __tablename__ = "action_intent_authority_bindings"
    __table_args__ = (
        CheckConstraint(
            "author_type IN ("
            + ", ".join(f"'{author}'" for author in ACTION_INTENT_AUTHORS)
            + ")",
            name="ck_action_intent_authority_bindings_author_type_closed",
        ),
        CheckConstraint(
            "execution_allowed = 0",
            name="ck_action_intent_authority_bindings_execution_allowed_false",
        ),
        CheckConstraint(
            "authority_transition = 0",
            name="ck_action_intent_authority_bindings_authority_transition_false",
        ),
    )

    binding_id: str = Field(primary_key=True)
    action_intent_id: str = Field(foreign_key="action_intents.action_intent_id", index=True)
    proposal_id: str = Field(foreign_key="proposals.proposal_id", index=True)
    source_action_intent_receipt_ref: str | None = None
    author_type: str
    author_id: str
    source_rule_ref: str | None = None
    agent_authority_grant_id: str | None = Field(
        default=None,
        foreign_key="agent_authority_grants.agent_authority_grant_id",
        index=True,
    )
    capital_mandate_id: str | None = Field(
        default=None,
        foreign_key="capital_mandates.capital_mandate_id",
        index=True,
    )
    requested_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    validated_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    allowed: bool = False
    deny_reasons: list[str] = Field(default_factory=list, sa_column=json_list_column())
    binding_deny_reasons: list[str] = Field(default_factory=list, sa_column=json_list_column())
    grant_deny_reasons: list[str] = Field(default_factory=list, sa_column=json_list_column())
    warnings: list[str] = Field(default_factory=list, sa_column=json_list_column())
    grant_validation_result: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=json_dict_column(),
    )
    grant_receipt_ref: str | None = None
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    non_claims: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_ref: str | None = None
    authority_level: AuthorityLevel = "authority_admission"
    execution_allowed: bool = False
    authority_transition: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("author_type")
    @classmethod
    def require_known_author_type(cls, value: str) -> str:
        if value not in ACTION_INTENT_AUTHORS:
            raise ValueError(f"author_type must be one of {ACTION_INTENT_AUTHORS}")
        return value

    @field_validator("author_id")
    @classmethod
    def require_author_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("authority binding requires author_id")
        return value

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("authority bindings never carry execution authority")
        return False

    @field_validator("authority_transition")
    @classmethod
    def reject_authority_transition(cls, value: bool) -> bool:
        if value:
            raise ValueError("authority bindings never carry authority transitions")
        return False


class ActionIntentSimulationReport(StateCoreBase, table=True):
    """Preflight-bound qualitative simulation report for an ActionIntentCandidate.

    The report records a downstream read of a specific action-intent receipt and
    a specific system-recomputed action preflight hash. It is descriptive only:
    no order ticket, broker instruction, approval, or execution authorization.
    """

    __tablename__ = "action_intent_simulation_reports"
    __table_args__ = (
        CheckConstraint(
            "execution_allowed = 0",
            name="ck_action_intent_sim_reports_execution_allowed_false",
        ),
        CheckConstraint(
            "authority_transition = 0",
            name="ck_action_intent_sim_reports_authority_transition_false",
        ),
        CheckConstraint(
            "scenario_mode IN ("
            + ", ".join(f"'{mode}'" for mode in ACTION_INTENT_SIMULATION_SCENARIO_MODES)
            + ")",
            name="ck_action_intent_sim_reports_scenario_mode_closed",
        ),
        CheckConstraint(
            "simulation_status IN ("
            + ", ".join(f"'{status}'" for status in ACTION_INTENT_SIMULATION_STATUSES)
            + ")",
            name="ck_action_intent_sim_reports_status_closed",
        ),
    )

    simulation_report_id: str = Field(primary_key=True)
    action_intent_id: str = Field(foreign_key="action_intents.action_intent_id", index=True)
    proposal_id: str = Field(foreign_key="proposals.proposal_id", index=True)
    source_action_intent_receipt_ref: str
    source_action_preflight_report_hash: str
    source_action_preflight_status: str
    source_action_preflight_finding_codes: list[str] = Field(
        default_factory=list,
        sa_column=json_list_column(),
    )
    acknowledged_preflight_warning_codes: list[str] = Field(
        default_factory=list,
        sa_column=json_list_column(),
    )
    scenario_mode: str = "descriptive_v0"
    simulation_status: str = "complete"
    risk_posture: str
    risk_direction: str
    affected_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    current_state_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    missing_data: list[str] = Field(default_factory=list, sa_column=json_list_column())
    assumptions: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    qualitative_impact: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    numeric_impact: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    next_actions: list[str] = Field(default_factory=list, sa_column=json_list_column())
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    non_claims: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_ref: str | None = None
    authority_level: AuthorityLevel = "needs_human_confirm"
    execution_allowed: bool = False
    authority_transition: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("simulation reports never carry execution authority")
        return False

    @field_validator("authority_transition")
    @classmethod
    def reject_authority_transition(cls, value: bool) -> bool:
        if value:
            raise ValueError("simulation reports never carry authority transitions")
        return False


class TradePlanCandidate(StateCoreBase, table=True):
    """Pre-trade plan candidate derived from a preflight-bound simulation report.

    This is not an order ticket, broker instruction, authority contract, or
    execution authorization. It records plan direction, scope, caps, and
    constraints for later human/authority review, but it cannot be submitted.
    """

    __tablename__ = "trade_plan_candidates"
    __table_args__ = (
        CheckConstraint(
            "execution_allowed = 0",
            name="ck_trade_plan_candidates_execution_allowed_false",
        ),
        CheckConstraint(
            "authority_transition = 0",
            name="ck_trade_plan_candidates_authority_transition_false",
        ),
        CheckConstraint(
            "submitted_to_broker = 0",
            name="ck_trade_plan_candidates_submitted_to_broker_false",
        ),
        CheckConstraint(
            "plan_direction IN ("
            + ", ".join(f"'{direction}'" for direction in TRADE_PLAN_CANDIDATE_DIRECTIONS)
            + ")",
            name="ck_trade_plan_candidates_direction_closed",
        ),
        CheckConstraint(
            "candidate_status IN ("
            + ", ".join(f"'{status}'" for status in TRADE_PLAN_CANDIDATE_STATUSES)
            + ")",
            name="ck_trade_plan_candidates_status_closed",
        ),
    )

    trade_plan_candidate_id: str = Field(primary_key=True)
    action_intent_id: str = Field(foreign_key="action_intents.action_intent_id", index=True)
    simulation_report_id: str = Field(
        foreign_key="action_intent_simulation_reports.simulation_report_id",
        index=True,
    )
    proposal_id: str = Field(foreign_key="proposals.proposal_id", index=True)
    source_action_intent_receipt_ref: str
    source_action_preflight_report_hash: str
    source_simulation_report_receipt_ref: str
    source_action_preflight_status: str
    source_action_preflight_finding_codes: list[str] = Field(
        default_factory=list,
        sa_column=json_list_column(),
    )
    acknowledged_preflight_warning_codes: list[str] = Field(
        default_factory=list,
        sa_column=json_list_column(),
    )
    plan_reason: str
    plan_direction: str
    target_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    instrument_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    account_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    risk_constraints: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    notional_cap: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    percent_cap: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    time_window: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    required_authority_level: str = "authority_contract_required"
    candidate_status: str = "needs_authority_contract"
    validation_findings: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=json_list_column(),
    )
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    preflight_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    non_claims: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_ref: str | None = None
    authority_level: AuthorityLevel = "needs_human_confirm"
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("trade plan candidates never carry execution authority")
        return False

    @field_validator("authority_transition")
    @classmethod
    def reject_authority_transition(cls, value: bool) -> bool:
        if value:
            raise ValueError("trade plan candidates never carry authority transitions")
        return False

    @field_validator("submitted_to_broker")
    @classmethod
    def reject_broker_submission(cls, value: bool) -> bool:
        if value:
            raise ValueError("trade plan candidates are never submitted to brokers")
        return False


class TradePlanReviewGate(StateCoreBase, table=True):
    """Review gate for deciding whether a plan may enter ticket staging.

    This gate is not an order ticket, broker instruction, authority contract,
    suitability certification, or execution authorization. It only records a
    human review result for the next candidate staging step.
    """

    __tablename__ = "trade_plan_review_gates"
    __table_args__ = (
        CheckConstraint(
            "execution_allowed = 0",
            name="ck_trade_plan_review_gates_execution_allowed_false",
        ),
        CheckConstraint(
            "authority_transition = 0",
            name="ck_trade_plan_review_gates_authority_transition_false",
        ),
        CheckConstraint(
            "submitted_to_broker = 0",
            name="ck_trade_plan_review_gates_submitted_to_broker_false",
        ),
        CheckConstraint(
            "creates_order_ticket = 0",
            name="ck_trade_plan_review_gates_creates_order_ticket_false",
        ),
        CheckConstraint(
            "review_decision IN ("
            + ", ".join(f"'{decision}'" for decision in TRADE_PLAN_REVIEW_GATE_DECISIONS)
            + ")",
            name="ck_trade_plan_review_gates_decision_closed",
        ),
        CheckConstraint(
            "reviewer_type IN ("
            + ", ".join(
                f"'{reviewer_type}'" for reviewer_type in TRADE_PLAN_REVIEW_GATE_REVIEWER_TYPES
            )
            + ")",
            name="ck_trade_plan_review_gates_reviewer_type_closed",
        ),
    )

    review_gate_id: str = Field(primary_key=True)
    trade_plan_candidate_id: str = Field(
        foreign_key="trade_plan_candidates.trade_plan_candidate_id",
        index=True,
    )
    action_intent_id: str = Field(foreign_key="action_intents.action_intent_id", index=True)
    simulation_report_id: str = Field(
        foreign_key="action_intent_simulation_reports.simulation_report_id",
        index=True,
    )
    proposal_id: str = Field(foreign_key="proposals.proposal_id", index=True)
    source_trade_plan_candidate_receipt_ref: str
    source_action_intent_receipt_ref: str
    source_action_preflight_report_hash: str
    source_simulation_report_receipt_ref: str
    review_decision: str
    reviewer_type: str = "human"
    reviewer_id: str
    review_reason: str
    review_context: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    review_findings: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=json_list_column(),
    )
    deny_reasons: list[str] = Field(default_factory=list, sa_column=json_list_column())
    candidate_validation_finding_codes: list[str] = Field(
        default_factory=list,
        sa_column=json_list_column(),
    )
    may_enter_order_ticket_candidate_staging: bool = False
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    preflight_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    non_claims: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_ref: str | None = None
    authority_level: AuthorityLevel = "needs_human_confirm"
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False
    creates_order_ticket: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("reviewer_id", "review_reason")
    @classmethod
    def require_named_reviewer_and_reason(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("trade plan review gate requires reviewer_id and reason")
        return value

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("trade plan review gates never carry execution authority")
        return False

    @field_validator("authority_transition")
    @classmethod
    def reject_authority_transition(cls, value: bool) -> bool:
        if value:
            raise ValueError("trade plan review gates never carry authority transitions")
        return False

    @field_validator("submitted_to_broker")
    @classmethod
    def reject_broker_submission(cls, value: bool) -> bool:
        if value:
            raise ValueError("trade plan review gates are never broker submissions")
        return False

    @field_validator("creates_order_ticket")
    @classmethod
    def reject_order_ticket_creation(cls, value: bool) -> bool:
        if value:
            raise ValueError("trade plan review gates never create order tickets")
        return False
