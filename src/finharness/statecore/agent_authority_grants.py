"""Receipt-backed AgentAuthorityGrant authority credentials.

Agent authority grants are mandate-bound credentials, not execution authority.
They must cite an active CapitalMandate at creation time and are dynamically
validated against the current mandate state at use time.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.project_paths import ROOT
from finharness.statecore.capital_mandates import (
    DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT,
    capital_mandate_series_owner,
    resolve_capital_mandate,
)
from finharness.statecore.models import (
    CAPITAL_MANDATE_AUTONOMY_LEVELS,
    AgentAuthorityGrant,
    AgentAuthorityGrantConsumption,
    CapitalMandate,
    CapitalMandateVersion,
    ReceiptIndex,
)
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.store import StateCoreStoreError, write_records

DEFAULT_AGENT_AUTHORITY_GRANT_RECEIPT_ROOT = DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT

AGENT_AUTHORITY_GRANT_NON_CLAIMS = (
    "AgentAuthorityGrant is a mandate-bound authority credential, not authentication.",
    "AgentAuthorityGrant does not approve trade plans or investment decisions.",
    "AgentAuthorityGrant does not submit orders or create broker authority.",
    "AgentAuthorityGrant does not bypass preflight or authorize execution.",
)

AgentAuthorityGrantDenyReason = Literal[
    "grant_not_found",
    "grant_not_active",
    "grant_expired",
    "principal_mismatch",
    "agent_runtime_mismatch",
    "mandate_series_owner_conflict",
    "mandate_version_changed",
    "grant_exhausted",
    "grant_notional_exhausted",
    "nonce_replayed",
    "capital_mandate_not_found",
    "capital_mandate_not_active",
    "grant_scope_exceeds_mandate",
    "requested_scope_exceeds_grant",
    "forbidden_execution_semantics",
    "forbidden_approval_semantics",
    "forbidden_broker_semantics",
    "forbidden_preflight_bypass_semantics",
]

AGENT_AUTHORITY_GRANT_DENY_REASONS: tuple[str, ...] = (
    "grant_not_found",
    "grant_not_active",
    "grant_expired",
    "principal_mismatch",
    "agent_runtime_mismatch",
    "mandate_series_owner_conflict",
    "mandate_version_changed",
    "grant_exhausted",
    "grant_notional_exhausted",
    "nonce_replayed",
    "capital_mandate_not_found",
    "capital_mandate_not_active",
    "grant_scope_exceeds_mandate",
    "requested_scope_exceeds_grant",
    "forbidden_execution_semantics",
    "forbidden_approval_semantics",
    "forbidden_broker_semantics",
    "forbidden_preflight_bypass_semantics",
)

_AUTONOMY_RANK = {
    level: index for index, level in enumerate(CAPITAL_MANDATE_AUTONOMY_LEVELS)
}
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")
_FORBIDDEN_SCOPE_TOKENS: dict[str, AgentAuthorityGrantDenyReason] = {
    "execute": "forbidden_execution_semantics",
    "execution": "forbidden_execution_semantics",
    "live_execution": "forbidden_execution_semantics",
    "execution_authorization": "forbidden_execution_semantics",
    "approve": "forbidden_approval_semantics",
    "approval": "forbidden_approval_semantics",
    "approve_trade_plan": "forbidden_approval_semantics",
    "trade_plan_approval": "forbidden_approval_semantics",
    "submit_order": "forbidden_broker_semantics",
    "order_submit": "forbidden_broker_semantics",
    "order_ticket": "forbidden_broker_semantics",
    "broker": "forbidden_broker_semantics",
    "broker_submit": "forbidden_broker_semantics",
    "broker_submission": "forbidden_broker_semantics",
    "broker_authority": "forbidden_broker_semantics",
    "bypass_preflight": "forbidden_preflight_bypass_semantics",
    "preflight_bypass": "forbidden_preflight_bypass_semantics",
    "override_preflight": "forbidden_preflight_bypass_semantics",
    "override_policy": "forbidden_preflight_bypass_semantics",
}


class AgentAuthorityGrantValidationResult(BaseModel):
    """Structured allow/deny result for dynamic grant validation."""

    model_config = ConfigDict(from_attributes=True)

    allowed: bool
    grant_id: str
    capital_mandate_id: str | None = None
    agent_id: str | None = None
    deny_reasons: list[AgentAuthorityGrantDenyReason] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    scope_result: dict[str, bool] = Field(default_factory=dict)
    execution_allowed: bool = False
    authority_transition: bool = False


class AgentAuthorityGrantValidationError(ValueError):
    """Raised when an authority grant write crosses its policy boundary."""


class AgentAuthorityGrantConsumptionResult(BaseModel):
    """Receipt-backed result of one atomic, nonce-unique grant consumption."""

    consumption: AgentAuthorityGrantConsumption
    usage_count: int
    used_notional: Decimal
    remaining_uses: int | None = None
    remaining_notional: Decimal | None = None
    execution_allowed: bool = False
    authority_transition: bool = False


def record_agent_authority_grant(  # noqa: C901
    *,
    capital_mandate_id: str,
    agent_id: str,
    issued_by: str,
    issued_reason: str,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_AGENT_AUTHORITY_GRANT_RECEIPT_ROOT,
    grant_scope: Mapping[str, Any] | None = None,
    agent_profile_name: str | None = None,
    expires_at_utc: str | None = None,
    source_refs: Sequence[str] | None = None,
    receipt_refs: Sequence[str] | None = None,
    agent_authority_grant_id: str | None = None,
    created_at_utc: str | None = None,
    principal_id: str | None = None,
    agent_runtime_id: str | None = None,
    max_uses: int | None = None,
    max_total_notional: Decimal | str | None = None,
) -> AgentAuthorityGrant:
    """Create a receipt-backed active AgentAuthorityGrant.

    Creation fails closed unless the linked CapitalMandate exists, is active,
    and the requested grant scope is within the mandate's current scope.
    """
    created_at = created_at_utc or _now_utc()
    _require_written_context(
        capital_mandate_id=capital_mandate_id,
        agent_id=agent_id,
        issued_by=issued_by,
        issued_reason=issued_reason,
    )
    _validate_expiry(expires_at_utc, created_at_utc=created_at)
    scope = dict(grant_scope or {})
    if _forbidden_scope_reasons(scope):
        raise AgentAuthorityGrantValidationError("grant_scope contains forbidden semantics")

    mandate = _get_capital_mandate(engine, capital_mandate_id)
    if mandate is None:
        raise KeyError(capital_mandate_id)
    durable_owner = capital_mandate_series_owner(engine, capital_mandate_id)
    if durable_owner is None:
        raise AgentAuthorityGrantValidationError("capital mandate version is required")
    resolved_principal = principal_id or durable_owner
    if resolved_principal != durable_owner:
        raise AgentAuthorityGrantValidationError("grant principal must own mandate series")
    current_resolution = resolve_capital_mandate(
        principal_id=resolved_principal,
        engine=engine,
        at_utc=created_at,
    )
    mandate_version = current_resolution.version
    if (
        current_resolution.status != "active"
        or mandate_version is None
        or mandate_version.principal_id != resolved_principal
        or mandate_version.capital_mandate_id != capital_mandate_id
    ):
        raise AgentAuthorityGrantValidationError("capital mandate must resolve active")
    if not _scope_within_mandate(scope, mandate_version=mandate_version):
        raise AgentAuthorityGrantValidationError("grant_scope exceeds capital mandate scope")
    resolved_runtime = (agent_runtime_id or agent_id).strip()
    if not resolved_runtime:
        raise AgentAuthorityGrantValidationError("agent_runtime_id is required")
    if max_uses is not None and max_uses <= 0:
        raise AgentAuthorityGrantValidationError("max_uses must be positive")
    parsed_max_notional = (
        Decimal(str(max_total_notional)) if max_total_notional is not None else None
    )
    if parsed_max_notional is not None and parsed_max_notional <= 0:
        raise AgentAuthorityGrantValidationError("max_total_notional must be positive")
    mandate_notional = _money_amount(mandate_version.typed_limits.get("max_notional"))
    if parsed_max_notional is not None and (
        mandate_notional is None or parsed_max_notional > mandate_notional
    ):
        raise AgentAuthorityGrantValidationError(
            "max_total_notional exceeds capital mandate limit"
        )

    resolved_id = (
        _safe_id(agent_authority_grant_id)
        if agent_authority_grant_id
        else f"agent_authority_grant_{_stamp()}_{uuid4().hex[:8]}"
    )
    resolved_receipt_refs = list(receipt_refs or [])
    mandate_receipt_ref = mandate_version.receipt_ref or mandate.receipt_ref
    if mandate_receipt_ref and mandate_receipt_ref not in resolved_receipt_refs:
        resolved_receipt_refs.append(mandate_receipt_ref)

    receipt_id = f"receipt_agent_authority_grant_{_stamp()}_{uuid4().hex[:8]}"
    receipt_path = resolve_under(
        receipt_root,
        "agent-authority-grants",
        f"{receipt_id}.json",
    )
    grant = AgentAuthorityGrant(
        agent_authority_grant_id=resolved_id,
        capital_mandate_id=mandate.capital_mandate_id,
        mandate_version_id=mandate_version.mandate_version_id,
        principal_id=resolved_principal,
        agent_runtime_id=resolved_runtime,
        agent_id=agent_id.strip(),
        agent_profile_name=agent_profile_name,
        status="active",
        grant_scope=scope,
        issued_by=issued_by.strip(),
        issued_reason=issued_reason.strip(),
        issued_against_mandate_receipt_ref=mandate_receipt_ref,
        expires_at_utc=expires_at_utc,
        max_uses=max_uses,
        max_total_notional=parsed_max_notional,
        source_refs=list(source_refs or []),
        receipt_refs=resolved_receipt_refs,
        non_claims=list(AGENT_AUTHORITY_GRANT_NON_CLAIMS),
        receipt_ref=_display_path(receipt_path),
        execution_allowed=False,
        authority_transition=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    receipt_existed = receipt_path.exists()
    creation_validation = validate_agent_authority_grant(
        grant.agent_authority_grant_id,
        engine=engine,
        requested_scope=scope,
        now_utc=created_at,
        candidate_grant=grant,
    )
    if not creation_validation.allowed:
        raise AgentAuthorityGrantValidationError(
            "grant creation validation failed: "
            + ", ".join(creation_validation.deny_reasons)
        )

    atomic_write_json(
        receipt_path,
        _agent_authority_grant_receipt_payload(
            grant=grant,
            mandate=mandate,
            mandate_version=mandate_version,
            receipt_id=receipt_id,
            creation_validation=creation_validation,
        ),
    )
    display = _display_path(receipt_path)
    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="state_core_agent_authority_grant",
        path=display,
        created_at_utc=created_at,
        source_refs=[display, *grant.source_refs],
        refs=[
            grant.agent_authority_grant_id,
            grant.capital_mandate_id,
            grant.agent_id,
            *grant.receipt_refs,
        ],
    )
    try:
        write_records([grant, index], engine=engine)
    except StateCoreStoreError:
        if not receipt_existed:
            remove_file_best_effort(receipt_path)
        raise
    return grant


def validate_agent_authority_grant(  # noqa: C901
    grant_id: str,
    *,
    engine: Engine,
    requested_scope: Mapping[str, Any] | None = None,
    now_utc: str | None = None,
    principal_id: str | None = None,
    agent_runtime_id: str | None = None,
    nonce: str | None = None,
    requested_notional: Decimal | str | None = None,
    candidate_grant: AgentAuthorityGrant | None = None,
) -> AgentAuthorityGrantValidationResult:
    """Dynamically validate a grant against current grant and mandate state."""
    requested = dict(requested_scope or {})
    deny_reasons: list[AgentAuthorityGrantDenyReason] = []
    scope_result = {
        "requested_scope_within_grant": False,
        "grant_scope_within_mandate": False,
    }

    grant = candidate_grant or _get_agent_authority_grant(engine, grant_id)
    if grant is None:
        return AgentAuthorityGrantValidationResult(
            allowed=False,
            grant_id=grant_id,
            deny_reasons=["grant_not_found"],
            scope_result=scope_result,
        )

    if grant.status != "active":
        deny_reasons.append("grant_not_active")
    if _is_expired(grant.expires_at_utc, now_utc=now_utc):
        deny_reasons.append("grant_expired")
    if principal_id is not None and grant.principal_id != principal_id:
        deny_reasons.append("principal_mismatch")
    if agent_runtime_id is not None and grant.agent_runtime_id != agent_runtime_id:
        deny_reasons.append("agent_runtime_mismatch")

    mandate_version = _get_mandate_version(engine, grant.mandate_version_id)
    resolution = (
        resolve_capital_mandate(
            principal_id=grant.principal_id,
            engine=engine,
            at_utc=now_utc,
        )
        if grant.principal_id is not None
        else None
    )
    if grant.principal_id is None:
        deny_reasons.append("principal_mismatch")
    if resolution is not None and "mandate_series_owner_conflict" in resolution.deny_reasons:
        deny_reasons.append("mandate_series_owner_conflict")
    elif resolution is None or resolution.version is None:
        deny_reasons.append("capital_mandate_not_found")
    elif resolution.status != "active":
        deny_reasons.append("capital_mandate_not_active")
    if mandate_version is None or (
        mandate_version.principal_id != grant.principal_id
        or mandate_version.capital_mandate_id != grant.capital_mandate_id
    ):
        deny_reasons.append("mandate_version_changed")
    if resolution is not None and resolution.version is not None and (
        resolution.version.principal_id != grant.principal_id
        or resolution.version.capital_mandate_id != grant.capital_mandate_id
        or resolution.version.mandate_version_id != grant.mandate_version_id
    ):
        deny_reasons.append("mandate_version_changed")

    if candidate_grant is None:
        consumptions = _grant_consumptions(engine, grant.agent_authority_grant_id)
        usage_count = len(consumptions)
        used_notional = sum(
            (item.requested_notional for item in consumptions),
            start=Decimal("0"),
        )
        if grant.max_uses is not None and usage_count >= grant.max_uses:
            deny_reasons.append("grant_exhausted")
        parsed_requested_notional = (
            Decimal(str(requested_notional)) if requested_notional is not None else None
        )
        if grant.max_total_notional is not None and (
            used_notional >= grant.max_total_notional
            or (
                parsed_requested_notional is not None
                and used_notional + parsed_requested_notional > grant.max_total_notional
            )
        ):
            deny_reasons.append("grant_notional_exhausted")
        if nonce is not None and any(item.nonce == nonce for item in consumptions):
            deny_reasons.append("nonce_replayed")

    forbidden_reasons = _forbidden_scope_reasons(grant.grant_scope)
    forbidden_reasons.extend(_forbidden_scope_reasons(requested))
    for reason in forbidden_reasons:
        if reason not in deny_reasons:
            deny_reasons.append(reason)

    if mandate_version is not None:
        scope_result["grant_scope_within_mandate"] = _scope_within_mandate(
            grant.grant_scope,
            mandate_version=mandate_version,
        )
        if not scope_result["grant_scope_within_mandate"]:
            deny_reasons.append("grant_scope_exceeds_mandate")

    scope_result["requested_scope_within_grant"] = _scope_within_scope(
        requested,
        grant.grant_scope,
    )
    if not scope_result["requested_scope_within_grant"]:
        deny_reasons.append("requested_scope_exceeds_grant")

    unique_reasons = _dedupe_reasons(deny_reasons)
    return AgentAuthorityGrantValidationResult(
        allowed=not unique_reasons,
        grant_id=grant.agent_authority_grant_id,
        capital_mandate_id=grant.capital_mandate_id,
        agent_id=grant.agent_id,
        deny_reasons=unique_reasons,
        scope_result=scope_result,
        execution_allowed=False,
        authority_transition=False,
    )


def consume_agent_authority_grant(  # noqa: C901
    grant_id: str,
    *,
    principal_id: str,
    agent_runtime_id: str,
    nonce: str,
    requested_scope: Mapping[str, Any],
    requested_notional: Decimal | str,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_AGENT_AUTHORITY_GRANT_RECEIPT_ROOT,
    now_utc: str | None = None,
) -> AgentAuthorityGrantConsumptionResult:
    """Atomically consume one bounded use; validation alone never consumes."""

    if not nonce.strip():
        raise AgentAuthorityGrantValidationError("nonce is required")
    notional = Decimal(str(requested_notional))
    if notional < 0:
        raise AgentAuthorityGrantValidationError("requested_notional must be non-negative")
    validation = validate_agent_authority_grant(
        grant_id,
        engine=engine,
        requested_scope=requested_scope,
        now_utc=now_utc,
        principal_id=principal_id,
        agent_runtime_id=agent_runtime_id,
        nonce=nonce,
        requested_notional=notional,
    )
    if not validation.allowed:
        raise AgentAuthorityGrantValidationError(
            "grant consumption denied: " + ", ".join(validation.deny_reasons)
        )
    validated_grant = _get_agent_authority_grant(engine, grant_id)
    per_use_notional = (
        _money_amount(validated_grant.grant_scope.get("max_notional"))
        if validated_grant is not None
        else None
    )
    if per_use_notional is not None and notional > per_use_notional:
        raise AgentAuthorityGrantValidationError("requested_scope_exceeds_grant")
    created_at = now_utc or _now_utc()
    receipt_id = f"receipt_agent_authority_grant_consumption_{_stamp()}_{uuid4().hex[:8]}"
    receipt_path = resolve_under(
        receipt_root,
        "agent-authority-grant-consumptions",
        f"{receipt_id}.json",
    )
    receipt_existed = receipt_path.exists()
    try:
        with Session(engine) as session:
            if engine.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            grant = session.exec(
                select(AgentAuthorityGrant)
                .where(AgentAuthorityGrant.agent_authority_grant_id == grant_id)
                .with_for_update()
            ).one_or_none()
            if grant is None or grant.mandate_version_id is None:
                raise AgentAuthorityGrantValidationError("grant is not AUTH-03 bound")
            locked_validation = validate_agent_authority_grant(
                grant_id,
                engine=engine,
                requested_scope=requested_scope,
                now_utc=now_utc,
                principal_id=principal_id,
                agent_runtime_id=agent_runtime_id,
                nonce=nonce,
                requested_notional=notional,
            )
            if not locked_validation.allowed:
                raise AgentAuthorityGrantValidationError(
                    "grant consumption denied under lock: "
                    + ", ".join(locked_validation.deny_reasons)
                )
            validation = locked_validation
            existing = list(
                session.exec(
                    select(AgentAuthorityGrantConsumption).where(
                        AgentAuthorityGrantConsumption.agent_authority_grant_id == grant_id
                    )
                ).all()
            )
            if any(item.nonce == nonce for item in existing):
                raise AgentAuthorityGrantValidationError("nonce_replayed")
            usage_count = len(existing)
            used_notional = sum(
                (item.requested_notional for item in existing),
                start=Decimal("0"),
            )
            if grant.max_uses is not None and usage_count >= grant.max_uses:
                raise AgentAuthorityGrantValidationError("grant_exhausted")
            if (
                grant.max_total_notional is not None
                and used_notional + notional > grant.max_total_notional
            ):
                raise AgentAuthorityGrantValidationError("grant_notional_exhausted")
            consumption = AgentAuthorityGrantConsumption(
                grant_consumption_id=f"grant_consumption_{_stamp()}_{uuid4().hex[:8]}",
                agent_authority_grant_id=grant_id,
                principal_id=principal_id,
                agent_runtime_id=agent_runtime_id,
                mandate_version_id=grant.mandate_version_id,
                nonce=nonce.strip(),
                requested_scope=dict(requested_scope),
                requested_notional=notional,
                receipt_ref=_display_path(receipt_path),
                created_at_utc=created_at,
                as_of_utc=created_at,
            )
            next_count = usage_count + 1
            next_notional = used_notional + notional
            payload = {
                "receipt_id": receipt_id,
                "kind": "state_core_agent_authority_grant_consumption",
                "created_at_utc": created_at,
                "consumption": consumption.model_dump(mode="json"),
                "validation": validation.model_dump(mode="json"),
                "usage_after": {
                    "usage_count": next_count,
                    "used_notional": str(next_notional),
                },
                "execution_allowed": False,
                "authority_transition": False,
            }
            atomic_write_json(receipt_path, payload)
            session.add(consumption)
            session.add(
                ReceiptIndex(
                    receipt_id=receipt_id,
                    kind="state_core_agent_authority_grant_consumption",
                    path=_display_path(receipt_path),
                    created_at_utc=created_at,
                    source_refs=[_display_path(receipt_path)],
                    refs=[grant_id, grant.mandate_version_id, principal_id, agent_runtime_id],
                )
            )
            session.commit()
            return AgentAuthorityGrantConsumptionResult(
                consumption=consumption,
                usage_count=next_count,
                used_notional=next_notional,
                remaining_uses=(
                    grant.max_uses - next_count if grant.max_uses is not None else None
                ),
                remaining_notional=(
                    grant.max_total_notional - next_notional
                    if grant.max_total_notional is not None
                    else None
                ),
            )
    except Exception:
        if not receipt_existed:
            remove_file_best_effort(receipt_path)
        raise


def revoke_agent_authority_grant(
    grant_id: str,
    *,
    principal_id: str,
    reason: str,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_AGENT_AUTHORITY_GRANT_RECEIPT_ROOT,
    revoked_at_utc: str | None = None,
) -> AgentAuthorityGrant:
    """Revoke a principal-owned grant and append an audit receipt atomically."""

    if not reason.strip():
        raise AgentAuthorityGrantValidationError("revocation reason is required")
    timestamp = revoked_at_utc or _now_utc()
    receipt_id = f"receipt_agent_authority_grant_revoked_{_stamp()}_{uuid4().hex[:8]}"
    receipt_path = resolve_under(
        receipt_root,
        "agent-authority-grants",
        "lifecycle",
        f"{receipt_id}.json",
    )
    receipt_existed = receipt_path.exists()
    try:
        with Session(engine) as session:
            if engine.dialect.name == "sqlite":
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            grant = session.exec(
                select(AgentAuthorityGrant)
                .where(AgentAuthorityGrant.agent_authority_grant_id == grant_id)
                .with_for_update()
            ).one_or_none()
            if grant is None:
                raise KeyError(grant_id)
            if grant.principal_id != principal_id:
                raise AgentAuthorityGrantValidationError(
                    "grant revocation principal mismatch"
                )
            if grant.status not in {"active", "suspended"}:
                raise AgentAuthorityGrantValidationError(
                    f"cannot revoke grant in {grant.status} state"
                )
            prior = grant.model_dump(mode="json")
            receipt_ref = _display_path(receipt_path)
            grant.status = "revoked"
            grant.revoked_at_utc = timestamp
            grant.revoked_reason = reason.strip()
            grant.receipt_refs = [*grant.receipt_refs, receipt_ref]
            atomic_write_json(
                receipt_path,
                {
                    "receipt_id": receipt_id,
                    "kind": "state_core_agent_authority_grant_revoked",
                    "created_at_utc": timestamp,
                    "prior_grant": prior,
                    "grant_after": grant.model_dump(mode="json"),
                    "actor_principal_id": principal_id,
                    "reason": reason.strip(),
                    "execution_allowed": False,
                    "authority_transition": False,
                },
            )
            session.add(grant)
            session.add(
                ReceiptIndex(
                    receipt_id=receipt_id,
                    kind="state_core_agent_authority_grant_revoked",
                    path=receipt_ref,
                    created_at_utc=timestamp,
                    source_refs=[receipt_ref],
                    refs=[grant_id, grant.capital_mandate_id, principal_id],
                )
            )
            session.commit()
            session.refresh(grant)
            return grant
    except Exception:
        if not receipt_existed:
            remove_file_best_effort(receipt_path)
        raise


def list_agent_authority_grants(
    *,
    engine: Engine,
    agent_id: str | None = None,
) -> list[AgentAuthorityGrant]:
    with Session(engine) as session:
        statement = select(AgentAuthorityGrant).order_by(AgentAuthorityGrant.created_at_utc)
        if agent_id is not None:
            statement = statement.where(AgentAuthorityGrant.agent_id == agent_id)
        return list(session.exec(statement).all())


def _get_agent_authority_grant(
    engine: Engine,
    grant_id: str,
) -> AgentAuthorityGrant | None:
    with Session(engine) as session:
        return session.get(AgentAuthorityGrant, grant_id)


def _get_capital_mandate(
    engine: Engine,
    capital_mandate_id: str,
) -> CapitalMandate | None:
    with Session(engine) as session:
        return session.get(CapitalMandate, capital_mandate_id)


def _get_mandate_version(
    engine: Engine,
    mandate_version_id: str | None,
) -> CapitalMandateVersion | None:
    if mandate_version_id is None:
        return None
    with Session(engine) as session:
        return session.get(CapitalMandateVersion, mandate_version_id)


def _grant_consumptions(
    engine: Engine,
    grant_id: str,
) -> list[AgentAuthorityGrantConsumption]:
    with Session(engine) as session:
        return list(
            session.exec(
                select(AgentAuthorityGrantConsumption).where(
                    AgentAuthorityGrantConsumption.agent_authority_grant_id == grant_id
                )
            ).all()
        )


def _scope_within_mandate(
    scope: Mapping[str, Any],
    *,
    mandate_version: CapitalMandateVersion,
) -> bool:
    typed_limits = mandate_version.typed_limits
    policy = mandate_version.policy_payload
    return _scope_within_scope(
        scope,
        {
            "allowed_asset_classes": policy.get("allowed_asset_classes", []),
            "allowed_action_types": policy.get("allowed_action_types", []),
            "autonomy_level": policy.get("autonomy_level", "L0_observe_only"),
            "product_ids": typed_limits.get("product_ids", []),
            "instrument_ids": typed_limits.get("instrument_ids", []),
            "action_types": typed_limits.get("action_types", []),
            "max_notional": typed_limits.get("max_notional"),
        },
        restricted_asset_classes=policy.get("restricted_asset_classes", []),
        restricted_action_types=policy.get("restricted_action_types", []),
        unbounded_keys=("directions", "broker_ids"),
    )


def _scope_within_scope(  # noqa: C901
    requested: Mapping[str, Any],
    allowed: Mapping[str, Any],
    *,
    restricted_asset_classes: Sequence[str] | None = None,
    restricted_action_types: Sequence[str] | None = None,
    unbounded_keys: Sequence[str] = (),
) -> bool:
    requested_assets = _string_set(requested.get("allowed_asset_classes"))
    allowed_assets = _string_set(allowed.get("allowed_asset_classes"))
    restricted_assets = _string_set(restricted_asset_classes)
    if requested_assets - allowed_assets:
        return False
    if requested_assets & restricted_assets:
        return False

    requested_actions = _string_set(requested.get("allowed_action_types"))
    allowed_actions = _string_set(allowed.get("allowed_action_types"))
    restricted_actions = _string_set(restricted_action_types)
    if requested_actions - allowed_actions:
        return False
    if requested_actions & restricted_actions:
        return False

    for key in (
        "product_ids",
        "instrument_ids",
        "action_types",
        "directions",
        "broker_ids",
    ):
        requested_values = _string_set(requested.get(key))
        allowed_values = _string_set(allowed.get(key))
        if key in unbounded_keys:
            continue
        if requested_values and (not allowed_values or requested_values - allowed_values):
            return False

    requested_notional = _money_amount(requested.get("max_notional"))
    allowed_notional = _money_amount(allowed.get("max_notional"))
    if requested_notional is not None and (
        allowed_notional is None or requested_notional > allowed_notional
    ):
        return False

    requested_autonomy = requested.get("autonomy_level")
    if requested_autonomy is not None:
        allowed_autonomy = allowed.get("autonomy_level")
        if not isinstance(requested_autonomy, str) or not isinstance(allowed_autonomy, str):
            return False
        if requested_autonomy not in _AUTONOMY_RANK or allowed_autonomy not in _AUTONOMY_RANK:
            return False
        if _AUTONOMY_RANK[requested_autonomy] > _AUTONOMY_RANK[allowed_autonomy]:
            return False
    return True


def _forbidden_scope_reasons(
    payload: Mapping[str, Any] | Sequence[Any] | str | None,
) -> list[AgentAuthorityGrantDenyReason]:
    reasons: list[AgentAuthorityGrantDenyReason] = []
    for token in _scope_tokens(payload):
        reason = _FORBIDDEN_SCOPE_TOKENS.get(token)
        if reason is not None and reason not in reasons:
            reasons.append(reason)
    return reasons


def _scope_tokens(payload: Mapping[str, Any] | Sequence[Any] | str | None) -> list[str]:
    tokens: list[str] = []
    if payload is None:
        return tokens
    if isinstance(payload, str):
        normalized = _normalize_token(payload)
        if normalized:
            tokens.append(normalized)
        return tokens
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            tokens.extend(_scope_tokens(str(key)))
            tokens.extend(_scope_tokens(value))
        return tokens
    if isinstance(payload, Sequence) and not isinstance(payload, (bytes, bytearray)):
        for item in payload:
            tokens.extend(_scope_tokens(item))
    return tokens


def _normalize_token(value: str) -> str:
    parts = [part for part in _TOKEN_SPLIT.split(value.lower()) if part]
    return "_".join(parts)


def _string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return {str(item) for item in value}
    return set()


def _money_amount(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        value = value.get("amount")
    try:
        amount = Decimal(str(value))
    except Exception:
        return None
    return amount if amount >= 0 else None


def _dedupe_reasons(
    reasons: Sequence[AgentAuthorityGrantDenyReason],
) -> list[AgentAuthorityGrantDenyReason]:
    result: list[AgentAuthorityGrantDenyReason] = []
    for reason in AGENT_AUTHORITY_GRANT_DENY_REASONS:
        if reason in reasons:
            result.append(reason)  # type: ignore[arg-type]
    return result


def _validate_expiry(expires_at_utc: str | None, *, created_at_utc: str) -> None:
    if expires_at_utc is None:
        return
    expires = _parse_utc(expires_at_utc)
    created = _parse_utc(created_at_utc)
    if expires <= created:
        raise AgentAuthorityGrantValidationError("expires_at_utc must be after creation")


def _is_expired(expires_at_utc: str | None, *, now_utc: str | None) -> bool:
    if expires_at_utc is None:
        return False
    return _parse_utc(expires_at_utc) <= _parse_utc(now_utc or _now_utc())


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AgentAuthorityGrantValidationError(f"invalid UTC timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _require_written_context(
    *,
    capital_mandate_id: str,
    agent_id: str,
    issued_by: str,
    issued_reason: str,
) -> None:
    if not capital_mandate_id.strip():
        raise AgentAuthorityGrantValidationError("capital_mandate_id is required")
    if not agent_id.strip():
        raise AgentAuthorityGrantValidationError("agent_id is required")
    if not issued_by.strip():
        raise AgentAuthorityGrantValidationError("issued_by is required")
    if not issued_reason.strip():
        raise AgentAuthorityGrantValidationError("issued_reason is required")


def _agent_authority_grant_receipt_payload(
    *,
    grant: AgentAuthorityGrant,
    mandate: CapitalMandate,
    mandate_version: CapitalMandateVersion,
    receipt_id: str,
    creation_validation: AgentAuthorityGrantValidationResult,
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "state_core_agent_authority_grant",
        "created_at_utc": grant.created_at_utc,
        "agent_authority_grant": grant.model_dump(mode="json"),
        "source_capital_mandate": mandate.model_dump(mode="json"),
        "source_capital_mandate_version": mandate_version.model_dump(mode="json"),
        "creation_validation": creation_validation.model_dump(mode="json"),
        "governance_boundary": {
            "execution_allowed": False,
            "authority_transition": False,
            "mandate_bound_authority_credential": True,
            "dynamic_validation_required": True,
            "not_authentication": True,
            "not_trade_plan_approval": True,
            "not_order_ticket": True,
            "not_broker_submission": True,
            "not_preflight_bypass": True,
            "not_execution_authorization": True,
        },
        "non_claims": list(AGENT_AUTHORITY_GRANT_NON_CLAIMS),
    }


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
