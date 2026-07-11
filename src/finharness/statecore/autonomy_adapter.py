"""Resolve legacy StateCore authority objects into the autonomy control plane.

This adapter preserves current CapitalMandate and AgentAuthorityGrant storage
while exposing the Agent-native AUT0-AUT3 runtime vocabulary.  Higher autonomy
levels require future schema and authority programs; they are never inferred.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlmodel import Session

from finharness.agent_capabilities import tool_names_for_profile
from finharness.autonomy_control import (
    AgentActionClass,
    AgentAutonomyLevel,
    AutonomyMandate,
    legacy_autonomy_level,
)
from finharness.statecore.agent_authority_grants import validate_agent_authority_grant
from finharness.statecore.models import AgentAuthorityGrant, CapitalMandate


class RuntimeAutonomyMandateResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    resolved: bool
    mandate: AutonomyMandate | None = None
    deny_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def resolve_runtime_autonomy_mandate(
    grant_id: str,
    *,
    engine: Engine,
    now_utc: str | None = None,
) -> RuntimeAutonomyMandateResolution:
    """Build the effective runtime mandate after dynamic StateCore validation."""

    with Session(engine) as session:
        grant = session.get(AgentAuthorityGrant, grant_id)
        mandate = (
            session.get(CapitalMandate, grant.capital_mandate_id) if grant is not None else None
        )
    if grant is None:
        return RuntimeAutonomyMandateResolution(
            resolved=False,
            deny_reasons=("grant_not_found",),
        )
    validation = validate_agent_authority_grant(
        grant_id,
        engine=engine,
        requested_scope=grant.grant_scope,
        now_utc=now_utc,
    )
    if not validation.allowed or mandate is None:
        reasons = tuple(str(reason) for reason in validation.deny_reasons)
        if mandate is None and "capital_mandate_not_found" not in reasons:
            reasons = (*reasons, "capital_mandate_not_found")
        return RuntimeAutonomyMandateResolution(
            resolved=False,
            deny_reasons=reasons,
            warnings=tuple(validation.warnings),
        )

    requested_level = str(grant.grant_scope.get("autonomy_level", mandate.autonomy_level))
    autonomy = legacy_autonomy_level(requested_level)
    profile_tools = _profile_tools(grant.agent_profile_name)
    scoped_tools = _string_tuple(grant.grant_scope.get("allowed_tools"))
    effective_tools = (
        tuple(tool for tool in profile_tools if tool in scoped_tools)
        if scoped_tools
        else profile_tools
    )
    financial_actions = _effective_scope(
        grant.grant_scope.get("allowed_action_types"),
        mandate.allowed_action_types,
    )
    asset_classes = _effective_scope(
        grant.grant_scope.get("allowed_asset_classes"),
        mandate.allowed_asset_classes,
    )
    refs = tuple(
        dict.fromkeys(
            [
                *mandate.source_refs,
                *mandate.receipt_refs,
                *grant.source_refs,
                *grant.receipt_refs,
                *([mandate.receipt_ref] if mandate.receipt_ref else []),
                *([grant.receipt_ref] if grant.receipt_ref else []),
            ]
        )
    )
    runtime_mandate = AutonomyMandate(
        mandate_id=mandate.capital_mandate_id,
        authority_grant_id=grant.agent_authority_grant_id,
        principal_id=grant.issued_by,
        agent_id=grant.agent_id,
        status="active",
        granted_autonomy=autonomy,
        allowed_action_classes=_action_classes_for(autonomy),
        allowed_financial_action_types=financial_actions,
        allowed_asset_classes=asset_classes,
        allowed_tools=effective_tools,
        constraints={
            "limit_book": dict(mandate.limit_book),
            "grant_scope": dict(grant.grant_scope),
            "kill_switch_rules": list(mandate.kill_switch_rules),
            "restricted_action_types": list(mandate.restricted_action_types),
            "restricted_asset_classes": list(mandate.restricted_asset_classes),
        },
        kill_switch_engaged=_kill_switch_engaged(mandate.kill_switch_rules),
        expires_at_utc=grant.expires_at_utc,
        source_refs=refs,
    )
    return RuntimeAutonomyMandateResolution(
        resolved=True,
        mandate=runtime_mandate,
        warnings=tuple(validation.warnings),
    )


def _action_classes_for(level: AgentAutonomyLevel) -> tuple[AgentActionClass, ...]:
    by_level = {
        AgentAutonomyLevel.AUT0_CONTEXT_ASSISTANT: (
            AgentActionClass.OBSERVE_STATE,
        ),
        AgentAutonomyLevel.AUT1_TOOL_REVIEWER: (
            AgentActionClass.OBSERVE_STATE,
            AgentActionClass.GATHER_EVIDENCE,
        ),
        AgentAutonomyLevel.AUT2_DURABLE_LOOP: (
            AgentActionClass.OBSERVE_STATE,
            AgentActionClass.GATHER_EVIDENCE,
            AgentActionClass.PREPARE_REVIEW_PACKET,
        ),
        AgentAutonomyLevel.AUT3_DELEGATED_REVIEW: (
            AgentActionClass.OBSERVE_STATE,
            AgentActionClass.GATHER_EVIDENCE,
            AgentActionClass.PREPARE_REVIEW_PACKET,
            AgentActionClass.MAKE_PLANNING_DECISION,
        ),
    }
    return by_level[level]


def _profile_tools(profile_name: str | None) -> tuple[str, ...]:
    if profile_name is None:
        return ()
    try:
        return tool_names_for_profile(profile_name)
    except ValueError:
        return ()


def _effective_scope(raw: Any, fallback: Iterable[str]) -> tuple[str, ...]:
    scoped = _string_tuple(raw)
    return scoped if scoped else tuple(fallback)


def _string_tuple(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, (list, tuple, set)):
        return ()
    return tuple(str(item) for item in raw if str(item).strip())


def _kill_switch_engaged(rules: list[dict[str, Any]]) -> bool:
    return any(rule.get("engaged") is True for rule in rules)
