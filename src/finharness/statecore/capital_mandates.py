"""Receipt-backed CapitalMandate policy domain.

Capital mandates sit above the IPS as a human-attested policy domain for future
delegated capital authority. They are policy scaffolding only: no execution
authorization, no authority transition, no broker instruction, and no order
ticket.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, select

from finharness.authority_administration import (
    AUTHORITY_ADMINISTRATION_OPERATION_EFFECT,
    AuthorityAdministrationDecision,
    require_authority_administration,
)
from finharness.identity import OperatorContext
from finharness.ips import DEFAULT_IPS_RECEIPT_ROOT, current_ips
from finharness.project_paths import ROOT
from finharness.statecore.models import (
    CapitalMandate,
    CapitalMandateLifecycleEvent,
    CapitalMandateVersion,
    InvestmentPolicyStatement,
    ReceiptIndex,
)
from finharness.statecore.money import MonetaryAmount
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.store import StateCoreStoreError, upsert_records

DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT = DEFAULT_IPS_RECEIPT_ROOT

CAPITAL_MANDATE_NON_CLAIMS = (
    "CapitalMandate is a human-attested policy domain, not investment advice.",
    "CapitalMandate does not grant an Agent identity or delegated authority.",
    "CapitalMandate is not an AuthorityContract, order ticket, or broker instruction.",
    "CapitalMandate does not authorize execution or live capital movement.",
)

# Canonical principal-bound resolution order. The first three fields express
# domain/record chronology; the identifiers are stable lexical tie-breakers,
# not economic or authority priority.
CAPITAL_MANDATE_RESOLUTION_ORDER = (
    "effective_at_utc",
    "created_at_utc",
    "version_number",
    "capital_mandate_id",
    "mandate_version_id",
)
CAPITAL_MANDATE_LIFECYCLE_ORDER = (
    "effective_at_utc",
    "created_at_utc",
    "mandate_lifecycle_event_id",
)


class CapitalMandateValidationError(ValueError):
    """Raised when a capital mandate write would cross its policy boundary."""


class MandateStringScope(BaseModel):
    """Closed bounded set or an explicit wildcard owned by the mandate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["bounded", "wildcard"] = "bounded"
    values: tuple[str, ...] = ()

    def model_post_init(self, _context: object) -> None:
        if self.mode == "wildcard" and self.values:
            raise ValueError("wildcard mandate scope cannot also declare values")
        if any(
            not value.strip() or value != value.strip() or value == "*" for value in self.values
        ):
            raise ValueError("mandate scope values must be explicit non-wildcard strings")
        if len(self.values) != len(set(self.values)):
            raise ValueError("mandate scope values must be unique")


class CapitalMandateLimits(BaseModel):
    """Typed, closed limit book independent from free-form policy narrative."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    product_ids: tuple[str, ...] = ()
    instrument_ids: tuple[str, ...] = ()
    action_types: tuple[str, ...] = ()
    max_notional: MonetaryAmount | None = None
    max_actions_per_period: int | None = Field(default=None, gt=0)
    period_seconds: int | None = Field(default=None, gt=0)
    max_loss: MonetaryAmount | None = None
    direction_scope: MandateStringScope = Field(default_factory=MandateStringScope)
    broker_scope: MandateStringScope = Field(default_factory=MandateStringScope)

    def model_post_init(self, _context: object) -> None:
        if (self.max_actions_per_period is None) != (self.period_seconds is None):
            raise ValueError("frequency limit requires count and period_seconds")
        if self.max_notional is not None:
            self.max_notional.require_positive(field_name="max_notional")
        if self.max_loss is not None:
            self.max_loss.require_positive(field_name="max_loss")


class CapitalMandateKillSwitchScope(BaseModel):
    """Closed scope describing which bounded surfaces a kill switch freezes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    global_scope: bool = False
    product_ids: tuple[str, ...] = ()
    instrument_ids: tuple[str, ...] = ()
    action_types: tuple[str, ...] = ()


class ResolvedCapitalMandate(BaseModel):
    """Server-derived mandate status at one principal/time boundary."""

    model_config = ConfigDict(frozen=True)

    principal_id: str
    at_utc: str
    status: str
    version: CapitalMandateVersion | None
    lifecycle_event: CapitalMandateLifecycleEvent | None = None
    deny_reasons: tuple[str, ...] = ()
    execution_allowed: bool = False
    authority_transition: bool = False


def current_capital_mandate(engine: Engine) -> CapitalMandate | None:
    """Return a legacy global mirror row.

    This compatibility helper is non-authoritative and unsuitable for identity,
    mandate-currentness, lifecycle, or grant decisions. Authority consumers must
    call :func:`resolve_capital_mandate` with an authenticated principal.
    """
    with Session(engine) as session:
        statement = (
            select(CapitalMandate)
            .where(CapitalMandate.status == "active")
            .order_by(col(CapitalMandate.created_at_utc).desc())
            .limit(1)
        )
        return session.exec(statement).first()


def record_capital_mandate(
    *,
    operator_context: OperatorContext,
    profile_snapshot: Mapping[str, Any],
    investment_objectives: Mapping[str, Any],
    risk_profile: Mapping[str, Any],
    human_reason: str,
    explicit_confirmation: bool,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT,
    allowed_asset_classes: Sequence[str] | None = None,
    restricted_asset_classes: Sequence[str] | None = None,
    allowed_action_types: Sequence[str] | None = None,
    restricted_action_types: Sequence[str] | None = None,
    autonomy_level: str = "L1_candidate_only",
    limit_book: Mapping[str, Any] | None = None,
    kill_switch_rules: Sequence[Mapping[str, Any]] | None = None,
    review_cadence: Mapping[str, Any] | None = None,
    source_ips_id: str | None = None,
    source_refs: Sequence[str] | None = None,
    receipt_refs: Sequence[str] | None = None,
    capital_mandate_id: str | None = None,
    created_at_utc: str | None = None,
    typed_limits: Mapping[str, Any] | CapitalMandateLimits | None = None,
    kill_switch_scope: Mapping[str, Any] | CapitalMandateKillSwitchScope | None = None,
    effective_at_utc: str | None = None,
    expires_at_utc: str | None = None,
    authenticated_actor_receipt_ref: str | None = None,
) -> CapitalMandate:
    """Write a receipt-backed active CapitalMandate.

    Previously active mandates are marked ``superseded``. The receipt file is the
    source of truth; the SQLite row is the queryable mirror.
    """
    administration = require_authority_administration(
        context=operator_context,
        operation="mandate_create_or_replace",
    )
    human_attester = operator_context.principal.principal_id
    resolved_principal_id = operator_context.principal.principal_id
    _require_attestation(
        human_attester=resolved_principal_id,
        human_reason=human_reason,
        explicit_confirmation=explicit_confirmation,
    )
    created_at = _parse_utc(created_at_utc).isoformat() if created_at_utc else _now_utc()
    effective_at = _parse_utc(effective_at_utc or created_at).isoformat()
    expires_at = _parse_utc(expires_at_utc).isoformat() if expires_at_utc else None
    _require_ordered_time(effective_at, expires_at)
    parsed_limits = (
        typed_limits
        if isinstance(typed_limits, CapitalMandateLimits)
        else CapitalMandateLimits.model_validate(typed_limits or {})
    )
    parsed_kill_switch_scope = (
        kill_switch_scope
        if isinstance(kill_switch_scope, CapitalMandateKillSwitchScope)
        else CapitalMandateKillSwitchScope.model_validate(kill_switch_scope or {})
    )
    resolved_id = (
        _safe_id(capital_mandate_id)
        if capital_mandate_id
        else f"capital_mandate_{_stamp()}_{uuid4().hex[:8]}"
    )
    _require_mandate_series_owner(
        engine,
        capital_mandate_id=resolved_id,
        principal_id=resolved_principal_id,
    )
    source_ips = _resolve_source_ips(engine, source_ips_id=source_ips_id)
    resolved_receipt_refs = list(receipt_refs or [])
    if (
        source_ips
        and source_ips.receipt_ref
        and source_ips.receipt_ref not in resolved_receipt_refs
    ):
        resolved_receipt_refs.append(source_ips.receipt_ref)

    receipt_id = f"receipt_capital_mandate_{_stamp()}_{uuid4().hex[:8]}"
    receipt_path = resolve_under(receipt_root, "capital-mandates", f"{receipt_id}.json")
    mandate = CapitalMandate(
        capital_mandate_id=resolved_id,
        status="active",
        source_ips_id=source_ips.ips_id if source_ips else None,
        profile_snapshot=dict(profile_snapshot),
        investment_objectives=dict(investment_objectives),
        risk_profile=dict(risk_profile),
        allowed_asset_classes=list(allowed_asset_classes or []),
        restricted_asset_classes=list(restricted_asset_classes or []),
        allowed_action_types=list(allowed_action_types or []),
        restricted_action_types=list(restricted_action_types or []),
        autonomy_level=autonomy_level,
        limit_book=dict(limit_book or {}),
        kill_switch_rules=[dict(rule) for rule in (kill_switch_rules or [])],
        review_cadence=dict(review_cadence or {}),
        human_attester=human_attester.strip(),
        human_reason=human_reason.strip(),
        explicit_confirmation=True,
        source_refs=list(source_refs or []),
        receipt_refs=resolved_receipt_refs,
        non_claims=list(CAPITAL_MANDATE_NON_CLAIMS),
        receipt_ref=_display_path(receipt_path),
        execution_allowed=False,
        authority_transition=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    version = _build_mandate_version(
        mandate=mandate,
        principal_id=resolved_principal_id,
        typed_limits=parsed_limits,
        kill_switch_scope=parsed_kill_switch_scope,
        effective_at_utc=effective_at,
        expires_at_utc=expires_at,
        authenticated_actor_receipt_ref=authenticated_actor_receipt_ref,
        legacy_actor_label=operator_context.principal.legacy_label,
        engine=engine,
    )
    activation = _lifecycle_event(
        version=version,
        event_type="activated",
        actor_principal_id=resolved_principal_id,
        reason=human_reason,
        receipt_ref=_display_path(receipt_path),
        effective_at_utc=effective_at,
    )
    superseded = _supersede_active_mandates(
        engine,
        keep=resolved_id,
        principal_id=resolved_principal_id,
    )
    receipt_existed = receipt_path.exists()
    atomic_write_json(
        receipt_path,
        _capital_mandate_receipt_payload(
            mandate=mandate,
            version=version,
            activation=activation,
            receipt_id=receipt_id,
            source_ips=source_ips,
            administration=administration,
        ),
    )
    display = _display_path(receipt_path)
    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="state_core_capital_mandate",
        path=display,
        created_at_utc=created_at,
        source_refs=[display, *mandate.source_refs],
        refs=[resolved_id, *_source_ips_refs(mandate), *mandate.receipt_refs],
    )
    try:
        upsert_records([*superseded, mandate, version, activation, index], engine=engine)
    except StateCoreStoreError:
        if not receipt_existed:
            remove_file_best_effort(receipt_path)
        raise
    return mandate


def _resolve_source_ips(
    engine: Engine,
    *,
    source_ips_id: str | None,
) -> InvestmentPolicyStatement | None:
    if source_ips_id is None:
        return current_ips(engine)
    with Session(engine) as session:
        ips = session.get(InvestmentPolicyStatement, source_ips_id)
    if ips is None:
        raise KeyError(source_ips_id)
    return ips


def _require_attestation(
    *,
    human_attester: str,
    human_reason: str,
    explicit_confirmation: bool,
) -> None:
    if not human_attester.strip():
        raise CapitalMandateValidationError("human_attester is required")
    if not human_reason.strip():
        raise CapitalMandateValidationError("human_reason is required")
    if not explicit_confirmation:
        raise CapitalMandateValidationError("explicit_confirmation must be true")


def _capital_mandate_receipt_payload(
    *,
    mandate: CapitalMandate,
    version: CapitalMandateVersion,
    activation: CapitalMandateLifecycleEvent,
    receipt_id: str,
    source_ips: InvestmentPolicyStatement | None,
    administration: AuthorityAdministrationDecision,
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "state_core_capital_mandate",
        "created_at_utc": mandate.created_at_utc,
        "capital_mandate": mandate.model_dump(mode="json"),
        "mandate_version": version.model_dump(mode="json"),
        "lifecycle_event": activation.model_dump(mode="json"),
        "authority_administration": administration.model_dump(mode="json", by_alias=True),
        "source_ips": source_ips.model_dump(mode="json") if source_ips else None,
        "governance_boundary": {
            "execution_allowed": False,
            "authority_transition": False,
            "explicit_confirmation": True,
            "human_attested_policy_domain": True,
            "future_authority_basis": True,
            "not_execution_authorization": True,
            "not_agent_identity_grant": True,
            "not_authority_contract": True,
            "not_order_ticket": True,
        },
        "non_claims": list(CAPITAL_MANDATE_NON_CLAIMS),
    }


def _source_ips_refs(mandate: CapitalMandate) -> list[str]:
    return [mandate.source_ips_id] if mandate.source_ips_id else []


def capital_mandate_series_owner(
    engine: Engine,
    capital_mandate_id: str,
) -> str | None:
    """Return the one durable version owner, rejecting corrupted shared series."""

    with Session(engine) as session:
        return _capital_mandate_series_owner_in_session(session, capital_mandate_id)


def _capital_mandate_series_owner_in_session(
    session: Session,
    capital_mandate_id: str,
) -> str | None:
    owners = set(
        session.exec(
            select(CapitalMandateVersion.principal_id).where(
                CapitalMandateVersion.capital_mandate_id == capital_mandate_id
            )
        ).all()
    )
    if len(owners) > 1:
        raise CapitalMandateValidationError(
            "capital mandate series has multiple durable principal owners"
        )
    return next(iter(owners), None)


def _require_mandate_series_owner(
    engine: Engine,
    *,
    capital_mandate_id: str,
    principal_id: str,
) -> None:
    owner = capital_mandate_series_owner(engine, capital_mandate_id)
    if owner is not None:
        if owner != principal_id:
            raise CapitalMandateValidationError("capital mandate ID is owned by another principal")
        return
    with Session(engine) as session:
        legacy_row = session.get(CapitalMandate, capital_mandate_id)
    if legacy_row is not None:
        raise CapitalMandateValidationError(
            "legacy capital mandate durable owner unavailable; unverified labels cannot claim it"
        )


def _supersede_active_mandates(
    engine: Engine,
    *,
    keep: str,
    principal_id: str,
) -> list[CapitalMandate]:
    with Session(engine) as session:
        rows = session.exec(select(CapitalMandate).where(CapitalMandate.status == "active")).all()
    superseded: list[CapitalMandate] = []
    for row in rows:
        if row.capital_mandate_id == keep:
            continue
        if capital_mandate_series_owner(engine, row.capital_mandate_id) != principal_id:
            continue
        row.status = "superseded"
        superseded.append(row)
    return superseded


def resolve_capital_mandate(
    *,
    principal_id: str,
    engine: Engine,
    at_utc: str | None = None,
) -> ResolvedCapitalMandate:
    """Resolve the latest effective mandate and lifecycle state for a principal."""

    if not principal_id.strip():
        raise CapitalMandateValidationError("principal_id is required for mandate resolution")
    resolved_at = at_utc or _now_utc()
    with Session(engine) as session:
        return _resolve_capital_mandate_in_session(
            session,
            principal_id=principal_id,
            at_utc=resolved_at,
        )


def _resolve_capital_mandate_in_session(
    session: Session,
    *,
    principal_id: str,
    at_utc: str,
    lock: bool = False,
) -> ResolvedCapitalMandate:
    at_dt = _parse_utc(at_utc)
    version_statement = select(CapitalMandateVersion).where(
        CapitalMandateVersion.principal_id == principal_id
    )
    if lock:
        version_statement = version_statement.with_for_update()
    versions = session.exec(version_statement).all()
    effective_versions = [
        candidate for candidate in versions if _parse_utc(candidate.effective_at_utc) <= at_dt
    ]
    for candidate in effective_versions:
        try:
            owner = _capital_mandate_series_owner_in_session(
                session,
                candidate.capital_mandate_id,
            )
        except CapitalMandateValidationError:
            return ResolvedCapitalMandate(
                principal_id=principal_id,
                at_utc=at_utc,
                status="invalid",
                version=None,
                deny_reasons=("mandate_series_owner_conflict",),
            )
        if owner != principal_id:
            return ResolvedCapitalMandate(
                principal_id=principal_id,
                at_utc=at_utc,
                status="invalid",
                version=None,
                deny_reasons=("mandate_series_owner_conflict",),
            )
    version = max(
        effective_versions,
        key=_mandate_resolution_order_key,
        default=None,
    )
    if version is None:
        return ResolvedCapitalMandate(
            principal_id=principal_id,
            at_utc=at_utc,
            status="unavailable",
            version=None,
            deny_reasons=("no_effective_mandate",),
        )
    event_statement = select(CapitalMandateLifecycleEvent).where(
        CapitalMandateLifecycleEvent.mandate_version_id == version.mandate_version_id
    )
    if lock:
        event_statement = event_statement.with_for_update()
    events = session.exec(event_statement).all()
    effective_events = [event for event in events if _parse_utc(event.effective_at_utc) <= at_dt]
    latest_event = max(
        effective_events,
        key=_mandate_lifecycle_order_key,
        default=None,
    )
    if version.expires_at_utc and _parse_utc(version.expires_at_utc) <= at_dt:
        status = "expired"
    elif latest_event is None:
        status = "unavailable"
    else:
        status = {
            "activated": "active",
            "resumed": "active",
            "suspended": "suspended",
            "revoked": "revoked",
        }[latest_event.event_type]
    return ResolvedCapitalMandate(
        principal_id=principal_id,
        at_utc=at_utc,
        status=status,
        version=version,
        lifecycle_event=latest_event,
        deny_reasons=() if status == "active" else (f"mandate_{status}",),
    )


def suspend_capital_mandate(
    capital_mandate_id: str,
    *,
    operator_context: OperatorContext,
    reason: str,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT,
) -> CapitalMandateLifecycleEvent:
    return _record_lifecycle_command(
        capital_mandate_id,
        operator_context=operator_context,
        operation="mandate_suspend",
        event_type="suspended",
        reason=reason,
        engine=engine,
        receipt_root=receipt_root,
        effective_at_utc=None,
    )


def resume_capital_mandate(
    capital_mandate_id: str,
    *,
    operator_context: OperatorContext,
    reason: str,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT,
    effective_at_utc: str | None = None,
) -> CapitalMandateLifecycleEvent:
    return _record_lifecycle_command(
        capital_mandate_id,
        operator_context=operator_context,
        operation="mandate_resume",
        event_type="resumed",
        reason=reason,
        engine=engine,
        receipt_root=receipt_root,
        effective_at_utc=effective_at_utc,
    )


def revoke_capital_mandate(
    capital_mandate_id: str,
    *,
    operator_context: OperatorContext,
    reason: str,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT,
) -> CapitalMandateLifecycleEvent:
    return _record_lifecycle_command(
        capital_mandate_id,
        operator_context=operator_context,
        operation="mandate_revoke",
        event_type="revoked",
        reason=reason,
        engine=engine,
        receipt_root=receipt_root,
        effective_at_utc=None,
    )


def _record_lifecycle_command(
    capital_mandate_id: str,
    *,
    operator_context: OperatorContext,
    operation: Literal["mandate_suspend", "mandate_resume", "mandate_revoke"],
    event_type: str,
    reason: str,
    engine: Engine,
    receipt_root: str | Path,
    effective_at_utc: str | None,
) -> CapitalMandateLifecycleEvent:
    principal_id = operator_context.principal.principal_id
    actor_principal_id = principal_id
    if not reason.strip():
        raise CapitalMandateValidationError("mandate lifecycle reason is required")
    receipt_path: Path | None = None
    try:
        with Session(engine) as session:
            if engine.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            checked_at = _now_utc()
            administration = require_authority_administration(
                context=operator_context,
                operation=operation,
                checked_at_utc=checked_at,
            )
            if AUTHORITY_ADMINISTRATION_OPERATION_EFFECT[operation] == "reducing":
                resolved_at = checked_at
            else:
                resolved_at = _parse_utc(effective_at_utc or checked_at).isoformat()
            resolved = _resolve_capital_mandate_in_session(
                session,
                principal_id=principal_id,
                at_utc=resolved_at,
                lock=True,
            )
            if "mandate_series_owner_conflict" in resolved.deny_reasons:
                raise CapitalMandateValidationError("mandate_series_owner_conflict")
            version = resolved.version
            if version is None or version.capital_mandate_id != capital_mandate_id:
                raise CapitalMandateValidationError(
                    "current principal mandate does not match command"
                )
            allowed_from = {
                "suspended": {"active"},
                "resumed": {"suspended"},
                "revoked": {"active", "suspended"},
            }
            if resolved.status not in allowed_from[event_type]:
                raise CapitalMandateValidationError(
                    f"cannot apply {event_type} to mandate in {resolved.status} state"
                )
            receipt_id = f"receipt_capital_mandate_{event_type}_{_stamp()}_{uuid4().hex[:8]}"
            receipt_path = resolve_under(
                receipt_root,
                "capital-mandates",
                "lifecycle",
                f"{receipt_id}.json",
            )
            event = _lifecycle_event(
                version=version,
                event_type=event_type,
                actor_principal_id=actor_principal_id,
                reason=reason,
                receipt_ref=_display_path(receipt_path),
                effective_at_utc=resolved_at,
                created_at_utc=checked_at,
            )
            atomic_write_json(
                receipt_path,
                {
                    "receipt_id": receipt_id,
                    "kind": "capital_mandate_lifecycle",
                    "created_at_utc": checked_at,
                    "mandate_version": version.model_dump(mode="json"),
                    "lifecycle_event": event.model_dump(mode="json"),
                    "prior_resolution": resolved.model_dump(mode="json"),
                    "authority_administration": administration.model_dump(
                        mode="json",
                        by_alias=True,
                    ),
                    "execution_allowed": False,
                    "authority_transition": False,
                },
            )
            index = ReceiptIndex(
                receipt_id=receipt_id,
                kind="capital_mandate_lifecycle",
                path=_display_path(receipt_path),
                created_at_utc=checked_at,
                source_refs=[_display_path(receipt_path), *event.source_refs],
                refs=[capital_mandate_id, version.mandate_version_id, principal_id],
            )
            session.add(event)
            session.add(index)
            session.commit()
            session.refresh(event)
            return event
    except (SQLAlchemyError, OSError) as exc:
        if receipt_path is not None:
            remove_file_best_effort(receipt_path)
        raise StateCoreStoreError(f"mandate lifecycle atomic write failed: {exc}") from exc
    except Exception:
        if receipt_path is not None:
            remove_file_best_effort(receipt_path)
        raise


def _build_mandate_version(
    *,
    mandate: CapitalMandate,
    principal_id: str,
    typed_limits: CapitalMandateLimits,
    kill_switch_scope: CapitalMandateKillSwitchScope,
    effective_at_utc: str,
    expires_at_utc: str | None,
    authenticated_actor_receipt_ref: str | None,
    legacy_actor_label: str | None,
    engine: Engine,
) -> CapitalMandateVersion:
    with Session(engine) as session:
        previous = session.exec(
            select(CapitalMandateVersion)
            .where(
                CapitalMandateVersion.capital_mandate_id == mandate.capital_mandate_id,
                CapitalMandateVersion.principal_id == principal_id,
            )
            .order_by(col(CapitalMandateVersion.version_number).desc())
            .limit(1)
        ).first()
    version_number = (previous.version_number + 1) if previous else 1
    policy_payload = {
        "source_ips_id": mandate.source_ips_id,
        "profile_snapshot": mandate.profile_snapshot,
        "investment_objectives": mandate.investment_objectives,
        "risk_profile": mandate.risk_profile,
        "allowed_asset_classes": mandate.allowed_asset_classes,
        "restricted_asset_classes": mandate.restricted_asset_classes,
        "allowed_action_types": mandate.allowed_action_types,
        "restricted_action_types": mandate.restricted_action_types,
        "autonomy_level": mandate.autonomy_level,
        "limit_book": mandate.limit_book,
        "kill_switch_rules": mandate.kill_switch_rules,
        "review_cadence": mandate.review_cadence,
    }
    typed_payload = typed_limits.model_dump(mode="json")
    kill_switch_payload = kill_switch_scope.model_dump(mode="json")
    hash_payload = {
        "capital_mandate_id": mandate.capital_mandate_id,
        "principal_id": principal_id,
        "version_number": version_number,
        "policy_payload": policy_payload,
        "typed_limits": typed_payload,
        "kill_switch_scope": kill_switch_payload,
        "effective_at_utc": effective_at_utc,
        "expires_at_utc": expires_at_utc,
    }
    content_hash = hashlib.sha256(
        json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return CapitalMandateVersion(
        mandate_version_id=(f"{mandate.capital_mandate_id}:v{version_number}:{content_hash[:12]}"),
        capital_mandate_id=mandate.capital_mandate_id,
        principal_id=principal_id,
        version_number=version_number,
        mandate_content_hash=content_hash,
        effective_at_utc=effective_at_utc,
        expires_at_utc=expires_at_utc,
        supersedes_version_id=previous.mandate_version_id if previous else None,
        policy_payload=policy_payload,
        typed_limits=typed_payload,
        kill_switch_scope=kill_switch_payload,
        source_refs=mandate.source_refs,
        receipt_refs=mandate.receipt_refs,
        receipt_ref=mandate.receipt_ref,
        authenticated_actor_receipt_ref=authenticated_actor_receipt_ref,
        legacy_actor_label=legacy_actor_label,
        legacy_actor_label_verified=False,
        created_at_utc=mandate.created_at_utc,
        as_of_utc=mandate.as_of_utc,
    )


def _mandate_resolution_order_key(
    version: CapitalMandateVersion,
) -> tuple[Any, ...]:
    values: dict[str, Any] = {
        "effective_at_utc": _parse_utc(version.effective_at_utc),
        "created_at_utc": _parse_utc(version.created_at_utc),
        "version_number": version.version_number,
        "capital_mandate_id": version.capital_mandate_id,
        "mandate_version_id": version.mandate_version_id,
    }
    return tuple(values[field] for field in CAPITAL_MANDATE_RESOLUTION_ORDER)


def _mandate_lifecycle_order_key(
    event: CapitalMandateLifecycleEvent,
) -> tuple[Any, ...]:
    values: dict[str, Any] = {
        "effective_at_utc": _parse_utc(event.effective_at_utc),
        "created_at_utc": _parse_utc(event.created_at_utc),
        "mandate_lifecycle_event_id": event.mandate_lifecycle_event_id,
    }
    return tuple(values[field] for field in CAPITAL_MANDATE_LIFECYCLE_ORDER)


def _lifecycle_event(
    *,
    version: CapitalMandateVersion,
    event_type: str,
    actor_principal_id: str,
    reason: str,
    receipt_ref: str,
    effective_at_utc: str,
    created_at_utc: str | None = None,
) -> CapitalMandateLifecycleEvent:
    return CapitalMandateLifecycleEvent(
        mandate_lifecycle_event_id=(f"mandate_event_{_stamp()}_{uuid4().hex[:8]}"),
        capital_mandate_id=version.capital_mandate_id,
        mandate_version_id=version.mandate_version_id,
        principal_id=version.principal_id,
        event_type=event_type,
        effective_at_utc=effective_at_utc,
        authenticated_actor_principal_id=actor_principal_id,
        reason=reason.strip(),
        receipt_ref=receipt_ref,
        source_refs=list(version.source_refs),
        created_at_utc=created_at_utc or _now_utc(),
        as_of_utc=effective_at_utc,
    )


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise CapitalMandateValidationError("mandate timestamps require timezone")
    return parsed.astimezone(UTC)


def _require_ordered_time(effective_at_utc: str, expires_at_utc: str | None) -> None:
    effective = _parse_utc(effective_at_utc)
    if expires_at_utc is not None and _parse_utc(expires_at_utc) <= effective:
        raise CapitalMandateValidationError("mandate expiry must be after effective time")


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)
