"""SQLModel tables for the FinHarness state core.

The state core is queryable state, not evidence. Receipt files remain the
source of truth; these tables only store state snapshots, read indexes, and
governed proposals that never carry execution authority.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import field_validator
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field

from finharness.statecore.import_models import (  # noqa: F401
    CapitalImportSource,
    CapitalImportSourceAlias,
    ImportBatch,
    ImportTombstone,
    ReceiptManifest,
)
from finharness.statecore.model_base import (
    STATE_CORE_SCHEMA_VERSION,  # noqa: F401 - compatibility re-export
    AuthorityLevel,
    DecimalText,  # noqa: F401 - compatibility re-export
    SourcedStateCoreBase,  # noqa: F401 - compatibility re-export
    StateCoreBase,
    json_dict_column,
    json_list_column,
    money_column,
    utc_now_iso,
)
from finharness.statecore.money import normalize_currency_code

Decision = str
CAPITAL_MANDATE_STATUSES: tuple[str, ...] = ("active", "superseded")
CAPITAL_MANDATE_LIFECYCLE_EVENTS: tuple[str, ...] = (
    "activated",
    "suspended",
    "resumed",
    "revoked",
)
CAPITAL_MANDATE_AUTONOMY_LEVELS: tuple[str, ...] = (
    "L0_read_only",
    "L1_candidate_only",
    "L2_human_confirmed_apply",
    "L3_bounded_delegation_candidate",
)
AGENT_AUTHORITY_GRANT_STATUSES: tuple[str, ...] = ("active", "revoked", "suspended")


# ── Personal-finance models (extracted to personal_finance_models.py) ──
from finharness.statecore.personal_finance_models import (  # noqa: F401, E402
    Account,
    AccountIdentity,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    IdentityAlias,
    InstrumentIdentity,
    InsurancePolicy,
    Liability,
    Position,
    Snapshot,
    TaxEvent,
)


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
    decision_scaffold: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
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
    bound_proposal_version_id: str | None = None
    bound_proposal_receipt_ref: str | None = None
    authority_level: AuthorityLevel = "needs_human_confirm"
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("attester", "reason")
    @classmethod
    def require_written_human_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("attestation requires a named human and written reason")
        return value


def attestation_closes_current_review(
    attestation: Attestation,
    proposal: Proposal,
) -> bool:
    """Whether a terminal attestation is bound to the proposal's current revision."""

    if attestation.decision not in {"approved", "rejected"}:
        return False
    if proposal.receipt_ref is None:
        return True
    return proposal.receipt_ref in attestation.source_refs


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
        CheckConstraint("execution_allowed = 0", name="ck_review_events_execution_allowed_false"),
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
    bound_proposal_version_id: str | None = None
    bound_proposal_receipt_ref: str | None = None
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
                f"capital mandate autonomy_level must be one of {CAPITAL_MANDATE_AUTONOMY_LEVELS}"
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


class CapitalMandateVersion(StateCoreBase, table=True):
    """Immutable, principal-bound version of a CapitalMandate limit book."""

    __tablename__ = "capital_mandate_versions"
    __table_args__ = (
        CheckConstraint(
            "version_number > 0",
            name="ck_capital_mandate_versions_positive_version",
        ),
        CheckConstraint(
            "execution_allowed = 0",
            name="ck_capital_mandate_versions_execution_allowed_false",
        ),
        CheckConstraint(
            "authority_transition = 0",
            name="ck_capital_mandate_versions_authority_transition_false",
        ),
    )

    mandate_version_id: str = Field(primary_key=True)
    capital_mandate_id: str = Field(index=True)
    principal_id: str = Field(index=True)
    version_number: int
    mandate_content_hash: str = Field(index=True)
    effective_at_utc: str = Field(index=True)
    expires_at_utc: str | None = Field(default=None, index=True)
    supersedes_version_id: str | None = Field(default=None, index=True)
    policy_payload: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    typed_limits: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    kill_switch_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    receipt_ref: str | None = None
    authenticated_actor_receipt_ref: str | None = None
    legacy_actor_label: str | None = None
    legacy_actor_label_verified: bool = False
    execution_allowed: bool = False
    authority_transition: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator(
        "mandate_version_id",
        "capital_mandate_id",
        "principal_id",
        "mandate_content_hash",
        "effective_at_utc",
    )
    @classmethod
    def require_version_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("capital mandate version identity fields are required")
        return value.strip()

    @field_validator("version_number")
    @classmethod
    def require_positive_version(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("capital mandate version number must be positive")
        return value

    @field_validator("execution_allowed", "authority_transition")
    @classmethod
    def reject_runtime_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("capital mandate versions never authorize execution or transition")
        return False


class CapitalMandateLifecycleEvent(StateCoreBase, table=True):
    """Append-only suspend/resume/revoke history for a mandate series."""

    __tablename__ = "capital_mandate_lifecycle_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ("
            + ", ".join(f"'{event}'" for event in CAPITAL_MANDATE_LIFECYCLE_EVENTS)
            + ")",
            name="ck_capital_mandate_lifecycle_event_type_closed",
        ),
        CheckConstraint(
            "execution_allowed = 0",
            name="ck_capital_mandate_lifecycle_execution_allowed_false",
        ),
    )

    mandate_lifecycle_event_id: str = Field(primary_key=True)
    capital_mandate_id: str = Field(index=True)
    mandate_version_id: str = Field(
        foreign_key="capital_mandate_versions.mandate_version_id",
        index=True,
    )
    principal_id: str = Field(index=True)
    event_type: str
    effective_at_utc: str = Field(index=True)
    authenticated_actor_principal_id: str
    reason: str
    receipt_ref: str
    source_refs: list[str] = Field(default_factory=list, sa_column=json_list_column())
    execution_allowed: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator("event_type")
    @classmethod
    def require_lifecycle_event(cls, value: str) -> str:
        if value not in CAPITAL_MANDATE_LIFECYCLE_EVENTS:
            raise ValueError("unknown capital mandate lifecycle event")
        return value

    @field_validator("reason", "authenticated_actor_principal_id")
    @classmethod
    def require_event_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mandate lifecycle commands require actor and reason")
        return value.strip()


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
    mandate_version_id: str | None = Field(default=None, index=True)
    principal_id: str | None = Field(default=None, index=True)
    agent_runtime_id: str | None = Field(default=None, index=True)
    agent_id: str = Field(index=True)
    agent_profile_name: str | None = None
    status: str = "active"
    grant_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    issued_by: str
    issued_reason: str
    issued_against_mandate_receipt_ref: str | None = None
    expires_at_utc: str | None = None
    max_uses: int | None = None
    max_total_notional: Decimal | None = Field(
        default=None,
        sa_column=money_column(nullable=True),
    )
    notional_currency: str | None = None
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
                f"agent authority grant status must be one of {AGENT_AUTHORITY_GRANT_STATUSES}"
            )
        return value

    @field_validator("agent_id", "issued_by", "issued_reason")
    @classmethod
    def require_written_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agent authority grant requires agent, issuer, and reason")
        return value

    @field_validator("notional_currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_currency_code(value)

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


class AgentAuthorityGrantConsumption(StateCoreBase, table=True):
    """Append-only, nonce-unique consumption of a bounded authority grant."""

    __tablename__ = "agent_authority_grant_consumptions"
    __table_args__ = (
        UniqueConstraint(
            "agent_authority_grant_id",
            "nonce",
            name="uq_agent_authority_grant_consumption_nonce",
        ),
        CheckConstraint(
            "execution_allowed = 0",
            name="ck_agent_authority_grant_consumptions_execution_false",
        ),
    )

    grant_consumption_id: str = Field(primary_key=True)
    agent_authority_grant_id: str = Field(
        foreign_key="agent_authority_grants.agent_authority_grant_id",
        index=True,
    )
    principal_id: str = Field(index=True)
    agent_runtime_id: str = Field(index=True)
    mandate_version_id: str = Field(index=True)
    nonce: str = Field(index=True)
    requested_scope: dict[str, Any] = Field(default_factory=dict, sa_column=json_dict_column())
    requested_notional: Decimal = Field(default=Decimal("0"), sa_column=money_column())
    requested_notional_currency: str | None = None
    receipt_ref: str
    execution_allowed: bool = False
    authority_transition: bool = False
    created_at_utc: str = Field(default_factory=utc_now_iso)

    @field_validator(
        "grant_consumption_id",
        "agent_authority_grant_id",
        "principal_id",
        "agent_runtime_id",
        "mandate_version_id",
        "nonce",
        "receipt_ref",
    )
    @classmethod
    def require_consumption_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("grant consumption identity fields are required")
        return value.strip()

    @field_validator("requested_notional")
    @classmethod
    def require_non_negative_notional(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("requested_notional must be non-negative")
        return value

    @field_validator("requested_notional_currency")
    @classmethod
    def normalize_optional_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_currency_code(value)

    @field_validator("execution_allowed", "authority_transition")
    @classmethod
    def reject_consumption_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("grant consumption is not execution authority")
        return False
