"""Authority admission bindings for ActionIntentCandidate records.

An authority binding records whether an action intent's author may admit that
intent into the next capital-action governance step. It is deliberately thinner
than preflight: it validates actor authority and scope, preserves structured
deny reasons, and writes a receipt, but it does not approve, execute, create an
order ticket, submit to a broker, or bypass downstream checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.project_paths import ROOT
from finharness.statecore.agent_authority_grants import (
    AgentAuthorityGrantValidationResult,
    validate_agent_authority_grant,
)
from finharness.statecore.capital_mandates import (
    DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT,
)
from finharness.statecore.models import (
    ACTION_INTENT_AUTHORS,
    ActionIntent,
    ActionIntentAuthorityBinding,
    AgentAuthorityGrant,
    ReceiptIndex,
)
from finharness.statecore.proposals import _now_utc, _safe_id
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.store import StateCoreStoreError, write_records

DEFAULT_ACTION_INTENT_AUTHORITY_BINDING_RECEIPT_ROOT = (
    DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT
)

ActionIntentAuthorType = Literal["agent", "human", "system"]
ActionIntentAuthorityBindingDenyReason = Literal[
    "action_intent_not_found",
    "action_intent_author_type_missing",
    "action_intent_author_type_mismatch",
    "author_id_missing",
    "agent_intent_missing_grant",
    "agent_grant_not_found",
    "grant_agent_mismatch",
    "human_intent_unexpected_grant",
    "system_intent_missing_source_rule",
    "system_intent_unexpected_grant",
    "action_intent_scope_mismatch",
    "binding_result_denied",
]

ACTION_INTENT_AUTHORITY_BINDING_DENY_REASONS: tuple[str, ...] = (
    "action_intent_not_found",
    "action_intent_author_type_missing",
    "action_intent_author_type_mismatch",
    "author_id_missing",
    "agent_intent_missing_grant",
    "agent_grant_not_found",
    "grant_agent_mismatch",
    "human_intent_unexpected_grant",
    "system_intent_missing_source_rule",
    "system_intent_unexpected_grant",
    "action_intent_scope_mismatch",
    "binding_result_denied",
)

ACTION_INTENT_AUTHORITY_BINDING_NON_CLAIMS: tuple[str, ...] = (
    "ActionIntentAuthorityBinding only admits an ActionIntentCandidate into downstream checks.",
    "ActionIntentAuthorityBinding is not action preflight.",
    "ActionIntentAuthorityBinding is not trade-plan approval.",
    "ActionIntentAuthorityBinding does not create order tickets or broker submissions.",
    "ActionIntentAuthorityBinding does not bypass preflight or authorize execution.",
)


class ActionIntentAuthorityBindingValidationError(ValueError):
    """Raised when a binding request crosses the authority-admission boundary."""


class ActionIntentAuthorityBindingResult(BaseModel):
    """Structured authority admission result for downstream gates."""

    model_config = ConfigDict(from_attributes=True)

    allowed: bool
    action_intent_id: str
    author_type: ActionIntentAuthorType | str
    author_id: str | None = None
    agent_authority_grant_id: str | None = None
    capital_mandate_id: str | None = None
    requested_scope: dict[str, Any] = Field(default_factory=dict)
    validated_scope: dict[str, Any] = Field(default_factory=dict)
    deny_reasons: list[str] = Field(default_factory=list)
    source: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    grant_validation: dict[str, Any] = Field(default_factory=dict)
    execution_allowed: bool = False
    authority_transition: bool = False


@dataclass(frozen=True)
class GovernedActionIntentAuthorityBindingWrite:
    binding: ActionIntentAuthorityBinding
    result: ActionIntentAuthorityBindingResult
    receipt_ref: str
    execution_allowed: bool = False
    authority_transition: bool = False


def create_action_intent_authority_binding(
    *,
    action_intent_id: str,
    author_type: ActionIntentAuthorType,
    author_id: str,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_ACTION_INTENT_AUTHORITY_BINDING_RECEIPT_ROOT,
    agent_authority_grant_id: str | None = None,
    requested_scope: dict[str, Any] | None = None,
    source_rule_ref: str | None = None,
    source_refs: list[str] | None = None,
    binding_id: str | None = None,
    created_at_utc: str | None = None,
) -> GovernedActionIntentAuthorityBindingWrite:
    """Create a receipt-backed authority binding for an ActionIntentCandidate.

    Denied bindings are persisted too. Missing action intents still raise
    ``KeyError`` because there is no stable foreign-key target for a binding row.
    """

    created_at = created_at_utc or _now_utc()
    clean_author_type = str(author_type).strip()
    if clean_author_type not in ACTION_INTENT_AUTHORS:
        raise ActionIntentAuthorityBindingValidationError(
            f"author_type must be one of {ACTION_INTENT_AUTHORS}"
        )
    clean_author_id = author_id.strip()
    requested = dict(requested_scope or {})
    source_rule = _clean_optional(source_rule_ref)
    source_refs_clean = _dedupe_text(list(source_refs or []))

    with Session(engine) as session:
        action_intent = session.get(ActionIntent, action_intent_id)
    if action_intent is None:
        raise KeyError(action_intent_id)

    grant = _get_grant(engine, agent_authority_grant_id) if agent_authority_grant_id else None
    result = validate_action_intent_authority_binding(
        action_intent=action_intent,
        author_type=clean_author_type,
        author_id=clean_author_id,
        requested_scope=requested,
        agent_authority_grant_id=agent_authority_grant_id,
        agent_authority_grant=grant,
        source_rule_ref=source_rule,
        engine=engine,
        now_utc=created_at,
    )

    resolved_binding_id = (
        _safe_id(binding_id)
        if binding_id
        else f"action_intent_authority_binding_{_stamp()}_{uuid4().hex[:8]}"
    )
    receipt_id = f"receipt_{resolved_binding_id}"
    receipt_path = resolve_under(
        receipt_root,
        "action-intent-authority-bindings",
        f"{receipt_id}.json",
    )
    receipt_ref = _display_path(receipt_path)
    receipt_refs = _dedupe_text(
        [
            *(action_intent.receipt_refs or []),
            *([action_intent.receipt_ref] if action_intent.receipt_ref else []),
            *([grant.receipt_ref] if grant is not None and grant.receipt_ref else []),
            receipt_ref,
        ]
    )
    binding = ActionIntentAuthorityBinding(
        binding_id=resolved_binding_id,
        action_intent_id=action_intent.action_intent_id,
        proposal_id=action_intent.proposal_id,
        source_action_intent_receipt_ref=action_intent.receipt_ref,
        author_type=clean_author_type,
        author_id=clean_author_id,
        source_rule_ref=source_rule,
        agent_authority_grant_id=agent_authority_grant_id if grant is not None else None,
        capital_mandate_id=result.capital_mandate_id,
        requested_scope=requested,
        validated_scope=result.validated_scope,
        allowed=result.allowed,
        deny_reasons=result.deny_reasons,
        binding_deny_reasons=result.source.get("binding", []),
        grant_deny_reasons=result.source.get("grant_validation", []),
        warnings=result.warnings,
        grant_validation_result=result.grant_validation,
        grant_receipt_ref=grant.receipt_ref if grant is not None else None,
        source_refs=source_refs_clean,
        receipt_refs=receipt_refs,
        non_claims=list(ACTION_INTENT_AUTHORITY_BINDING_NON_CLAIMS),
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )

    receipt_existed = receipt_path.exists()
    atomic_write_json(
        receipt_path,
        _authority_binding_receipt_payload(
            receipt_id=receipt_id,
            binding=binding,
            action_intent=action_intent,
            result=result,
        ),
    )
    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="state_core_action_intent_authority_binding",
        path=receipt_ref,
        created_at_utc=created_at,
        source_refs=[receipt_ref, *source_refs_clean],
        refs=_dedupe_text(
            [
                binding.binding_id,
                action_intent.action_intent_id,
                action_intent.proposal_id,
                *([agent_authority_grant_id] if agent_authority_grant_id else []),
                *([binding.capital_mandate_id] if binding.capital_mandate_id else []),
                *binding.receipt_refs,
            ]
        ),
    )
    try:
        write_records([binding, index], engine=engine)
    except StateCoreStoreError:
        if not receipt_existed:
            remove_file_best_effort(receipt_path)
        raise
    return GovernedActionIntentAuthorityBindingWrite(
        binding=binding,
        result=result,
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
    )


def validate_action_intent_authority_binding(
    *,
    action_intent: ActionIntent,
    author_type: str,
    author_id: str,
    requested_scope: dict[str, Any],
    agent_authority_grant_id: str | None,
    agent_authority_grant: AgentAuthorityGrant | None,
    source_rule_ref: str | None,
    engine: Engine,
    now_utc: str | None = None,
) -> ActionIntentAuthorityBindingResult:
    """Validate an ActionIntent authority admission request without writing."""

    clean_author_type = author_type.strip()
    clean_author_id = author_id.strip()
    binding_reasons = _binding_layer_deny_reasons(
        action_intent=action_intent,
        author_type=clean_author_type,
        author_id=clean_author_id,
        requested_scope=requested_scope,
        agent_authority_grant_id=agent_authority_grant_id,
        agent_authority_grant=agent_authority_grant,
        source_rule_ref=source_rule_ref,
    )
    grant_validation = _grant_validation_for_binding(
        author_type=clean_author_type,
        agent_authority_grant_id=agent_authority_grant_id,
        agent_authority_grant=agent_authority_grant,
        requested_scope=requested_scope,
        engine=engine,
        now_utc=now_utc,
    )
    grant_reasons = _dedupe_text(
        list(grant_validation.deny_reasons) if grant_validation else []
    )
    allowed = not binding_reasons and not grant_reasons
    deny_reasons = _dedupe_text(
        [
            *binding_reasons,
            *grant_reasons,
            *(["binding_result_denied"] if binding_reasons or grant_reasons else []),
        ]
    )
    return ActionIntentAuthorityBindingResult(
        allowed=allowed,
        action_intent_id=action_intent.action_intent_id,
        author_type=clean_author_type,
        author_id=clean_author_id or None,
        agent_authority_grant_id=agent_authority_grant_id,
        capital_mandate_id=(
            grant_validation.capital_mandate_id if grant_validation else None
        ),
        requested_scope=requested_scope,
        validated_scope=_validated_scope_snapshot(
            action_intent=action_intent,
            author_type=clean_author_type,
            binding_reasons=binding_reasons,
            grant_validation=grant_validation,
        ),
        deny_reasons=deny_reasons,
        source={
            "binding": binding_reasons,
            "grant_validation": grant_reasons,
        },
        warnings=_binding_warnings(clean_author_type, binding_reasons),
        grant_validation=(
            grant_validation.model_dump(mode="json") if grant_validation else {}
        ),
        execution_allowed=False,
        authority_transition=False,
    )


def _binding_layer_deny_reasons(
    *,
    action_intent: ActionIntent,
    author_type: str,
    author_id: str,
    requested_scope: dict[str, Any],
    agent_authority_grant_id: str | None,
    agent_authority_grant: AgentAuthorityGrant | None,
    source_rule_ref: str | None,
) -> list[str]:
    reasons = _common_binding_deny_reasons(
        action_intent=action_intent,
        author_type=author_type,
        author_id=author_id,
        requested_scope=requested_scope,
    )
    reasons.extend(
        _author_specific_binding_deny_reasons(
            author_type=author_type,
            author_id=author_id,
            agent_authority_grant_id=agent_authority_grant_id,
            agent_authority_grant=agent_authority_grant,
            source_rule_ref=source_rule_ref,
        )
    )
    return _ordered_reasons(reasons)


def _common_binding_deny_reasons(
    *,
    action_intent: ActionIntent,
    author_type: str,
    author_id: str,
    requested_scope: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if author_type not in ACTION_INTENT_AUTHORS:
        reasons.append("action_intent_author_type_missing")
    if not author_id:
        reasons.append("author_id_missing")
    if action_intent.created_by != author_type:
        reasons.append("action_intent_author_type_mismatch")
    if not _scope_matches_action_intent(requested_scope, action_intent):
        reasons.append("action_intent_scope_mismatch")
    return reasons


def _author_specific_binding_deny_reasons(
    *,
    author_type: str,
    author_id: str,
    agent_authority_grant_id: str | None,
    agent_authority_grant: AgentAuthorityGrant | None,
    source_rule_ref: str | None,
) -> list[str]:
    if author_type == "agent":
        return _agent_binding_deny_reasons(
            author_id=author_id,
            agent_authority_grant_id=agent_authority_grant_id,
            agent_authority_grant=agent_authority_grant,
        )
    if author_type == "human" and agent_authority_grant_id:
        return ["human_intent_unexpected_grant"]
    if author_type == "system":
        reasons: list[str] = []
        if not source_rule_ref:
            reasons.append("system_intent_missing_source_rule")
        if agent_authority_grant_id:
            reasons.append("system_intent_unexpected_grant")
        return reasons
    return []


def _agent_binding_deny_reasons(
    *,
    author_id: str,
    agent_authority_grant_id: str | None,
    agent_authority_grant: AgentAuthorityGrant | None,
) -> list[str]:
    if not agent_authority_grant_id:
        return ["agent_intent_missing_grant"]
    if agent_authority_grant is None:
        return ["agent_grant_not_found"]
    if author_id and agent_authority_grant.agent_id != author_id:
        return ["grant_agent_mismatch"]
    return []


def _grant_validation_for_binding(
    *,
    author_type: str,
    agent_authority_grant_id: str | None,
    agent_authority_grant: AgentAuthorityGrant | None,
    requested_scope: dict[str, Any],
    engine: Engine,
    now_utc: str | None,
) -> AgentAuthorityGrantValidationResult | None:
    if (
        author_type != "agent"
        or agent_authority_grant_id is None
        or agent_authority_grant is None
    ):
        return None
    return validate_agent_authority_grant(
        agent_authority_grant_id,
        engine=engine,
        requested_scope=requested_scope,
        now_utc=now_utc,
    )


def _validated_scope_snapshot(
    *,
    action_intent: ActionIntent,
    author_type: str,
    binding_reasons: list[str],
    grant_validation: AgentAuthorityGrantValidationResult | None,
) -> dict[str, Any]:
    return {
        "within_binding": not binding_reasons,
        "within_grant": bool(grant_validation.allowed) if grant_validation else False,
        "within_mandate": bool(
            grant_validation
            and grant_validation.scope_result.get("grant_scope_within_mandate", False)
        ),
        "action_type": action_intent.action_type,
        "capital_mandate_id": (
            grant_validation.capital_mandate_id if grant_validation else None
        ),
        "non_agent_binding": author_type in {"human", "system"},
    }


def _binding_warnings(author_type: str, binding_reasons: list[str]) -> list[str]:
    if author_type in {"human", "system"} and not binding_reasons:
        return ["non_agent_binding_has_no_grant_validation"]
    return []


def get_action_intent_authority_binding(
    binding_id: str,
    *,
    engine: Engine,
) -> ActionIntentAuthorityBinding | None:
    with Session(engine) as session:
        return session.get(ActionIntentAuthorityBinding, binding_id)


def latest_action_intent_authority_binding(
    action_intent_id: str,
    *,
    engine: Engine,
) -> ActionIntentAuthorityBinding | None:
    with Session(engine) as session:
        statement = (
            select(ActionIntentAuthorityBinding)
            .where(ActionIntentAuthorityBinding.action_intent_id == action_intent_id)
        )
        bindings = list(session.exec(statement).all())
    if not bindings:
        return None
    return max(bindings, key=lambda binding: binding.created_at_utc)


def _get_grant(engine: Engine, grant_id: str | None) -> AgentAuthorityGrant | None:
    if not grant_id:
        return None
    with Session(engine) as session:
        return session.get(AgentAuthorityGrant, grant_id)


def _scope_matches_action_intent(
    requested_scope: dict[str, Any],
    action_intent: ActionIntent,
) -> bool:
    if not requested_scope:
        return False
    requested_actions = _string_set(requested_scope.get("allowed_action_types"))
    if not requested_actions:
        return False
    return action_intent.action_type in requested_actions


def _authority_binding_receipt_payload(
    *,
    receipt_id: str,
    binding: ActionIntentAuthorityBinding,
    action_intent: ActionIntent,
    result: ActionIntentAuthorityBindingResult,
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "state_core_action_intent_authority_binding",
        "created_at_utc": binding.created_at_utc,
        "action_intent_id": action_intent.action_intent_id,
        "source_action_intent_receipt_ref": action_intent.receipt_ref,
        "action_intent_authority_binding": binding.model_dump(mode="json"),
        "binding_result": result.model_dump(mode="json"),
        "governance_boundary": {
            "execution_allowed": False,
            "authority_transition": False,
            "authority_admission_only": True,
            "not_action_preflight": True,
            "not_trade_plan_approval": True,
            "not_order_ticket": True,
            "not_broker_submission": True,
            "not_preflight_bypass": True,
            "not_execution_authorization": True,
        },
        "non_claims": list(ACTION_INTENT_AUTHORITY_BINDING_NON_CLAIMS),
    }


def _ordered_reasons(reasons: list[str]) -> list[str]:
    ordered = [
        reason for reason in ACTION_INTENT_AUTHORITY_BINDING_DENY_REASONS if reason in reasons
    ]
    extras = [reason for reason in reasons if reason not in ordered]
    return [*ordered, *extras]


def _string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    clean = value.strip()
    return clean or None


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)
