"""Receipt-backed AgentAuthorityGrant authority credentials.

Agent authority grants are mandate-bound credentials, not execution authority.
They must cite an active CapitalMandate at creation time and are dynamically
validated against the current mandate state at use time.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.project_paths import ROOT
from finharness.statecore.capital_mandates import (
    DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT,
)
from finharness.statecore.models import (
    CAPITAL_MANDATE_AUTONOMY_LEVELS,
    AgentAuthorityGrant,
    CapitalMandate,
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


def record_agent_authority_grant(
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
    if mandate.status != "active":
        raise AgentAuthorityGrantValidationError("capital mandate must be active")
    if not _scope_within_mandate(scope, mandate):
        raise AgentAuthorityGrantValidationError("grant_scope exceeds capital mandate scope")

    resolved_id = (
        _safe_id(agent_authority_grant_id)
        if agent_authority_grant_id
        else f"agent_authority_grant_{_stamp()}_{uuid4().hex[:8]}"
    )
    resolved_receipt_refs = list(receipt_refs or [])
    if mandate.receipt_ref and mandate.receipt_ref not in resolved_receipt_refs:
        resolved_receipt_refs.append(mandate.receipt_ref)

    receipt_id = f"receipt_agent_authority_grant_{_stamp()}_{uuid4().hex[:8]}"
    receipt_path = resolve_under(
        receipt_root,
        "agent-authority-grants",
        f"{receipt_id}.json",
    )
    grant = AgentAuthorityGrant(
        agent_authority_grant_id=resolved_id,
        capital_mandate_id=mandate.capital_mandate_id,
        agent_id=agent_id.strip(),
        agent_profile_name=agent_profile_name,
        status="active",
        grant_scope=scope,
        issued_by=issued_by.strip(),
        issued_reason=issued_reason.strip(),
        issued_against_mandate_receipt_ref=mandate.receipt_ref,
        expires_at_utc=expires_at_utc,
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
        candidate_mandate=mandate,
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


def validate_agent_authority_grant(
    grant_id: str,
    *,
    engine: Engine,
    requested_scope: Mapping[str, Any] | None = None,
    now_utc: str | None = None,
    candidate_grant: AgentAuthorityGrant | None = None,
    candidate_mandate: CapitalMandate | None = None,
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

    mandate = candidate_mandate or _get_capital_mandate(engine, grant.capital_mandate_id)
    if mandate is None:
        deny_reasons.append("capital_mandate_not_found")
    elif mandate.status != "active":
        deny_reasons.append("capital_mandate_not_active")

    forbidden_reasons = _forbidden_scope_reasons(grant.grant_scope)
    forbidden_reasons.extend(_forbidden_scope_reasons(requested))
    for reason in forbidden_reasons:
        if reason not in deny_reasons:
            deny_reasons.append(reason)

    if mandate is not None:
        scope_result["grant_scope_within_mandate"] = _scope_within_mandate(
            grant.grant_scope,
            mandate,
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


def _scope_within_mandate(scope: Mapping[str, Any], mandate: CapitalMandate) -> bool:
    return _scope_within_scope(
        scope,
        {
            "allowed_asset_classes": mandate.allowed_asset_classes,
            "allowed_action_types": mandate.allowed_action_types,
            "autonomy_level": mandate.autonomy_level,
        },
        restricted_asset_classes=mandate.restricted_asset_classes,
        restricted_action_types=mandate.restricted_action_types,
    )


def _scope_within_scope(
    requested: Mapping[str, Any],
    allowed: Mapping[str, Any],
    *,
    restricted_asset_classes: Sequence[str] | None = None,
    restricted_action_types: Sequence[str] | None = None,
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
    receipt_id: str,
    creation_validation: AgentAuthorityGrantValidationResult,
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "state_core_agent_authority_grant",
        "created_at_utc": grant.created_at_utc,
        "agent_authority_grant": grant.model_dump(mode="json"),
        "source_capital_mandate": mandate.model_dump(mode="json"),
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
