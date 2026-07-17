"""Closed human-administrator policy for mandate and grant mutations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.identity import AuthenticationAssurance, OperatorContext

type AuthorityAdministrationOperation = Literal[
    "mandate_create_or_replace",
    "mandate_resume",
    "mandate_suspend",
    "mandate_revoke",
    "grant_create",
    "grant_revoke",
]
type AuthorityAdministrationDenyReason = Literal[
    "agent_runtime_forbidden",
    "human_principal_required",
    "authority_administrator_required",
    "assertion_subject_mismatch",
    "assertion_provider_mismatch",
    "authority_policy_version_mismatch",
    "authority_assertion_not_yet_valid",
    "authority_assertion_expired",
    "elevated_authentication_required",
    "unknown_authority_administration_operation",
]

AUTHORITY_ADMINISTRATION_POLICY_VERSION = "finharness.authority-administration.v1"
AUTHORITY_ADMINISTRATION_OPERATION_POLICY: dict[
    AuthorityAdministrationOperation, AuthenticationAssurance
] = {
    "mandate_create_or_replace": "elevated",
    "mandate_resume": "elevated",
    "mandate_suspend": "standard",
    "mandate_revoke": "standard",
    "grant_create": "elevated",
    "grant_revoke": "standard",
}
AUTHORITY_ADMINISTRATION_OPERATION_EFFECT: dict[
    AuthorityAdministrationOperation, Literal["expanding", "reducing"]
] = {
    "mandate_create_or_replace": "expanding",
    "mandate_resume": "expanding",
    "mandate_suspend": "reducing",
    "mandate_revoke": "reducing",
    "grant_create": "expanding",
    "grant_revoke": "reducing",
}


class AuthorityAdministrationDeniedError(ValueError):
    """Typed fail-closed denial at the authority-domain boundary."""

    def __init__(
        self,
        reason: AuthorityAdministrationDenyReason,
        *,
        operation: str,
    ) -> None:
        self.reason = reason
        self.operation = operation
        self.policy_version = AUTHORITY_ADMINISTRATION_POLICY_VERSION
        super().__init__(reason)


class AuthorityAdministrationDecision(BaseModel):
    """Evidence for one admitted command; never a reusable authority token."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_id: Literal["finharness.authority_administration_decision.v1"] = Field(
        default="finharness.authority_administration_decision.v1",
        alias="schema",
    )
    admitted: Literal[True] = True
    operation: AuthorityAdministrationOperation
    operation_effect: Literal["expanding", "reducing"]
    required_assurance: AuthenticationAssurance
    administrator_principal_id: str
    principal_kind: Literal["human"] = "human"
    direct_actor_kind: Literal["human"] = "human"
    agent_runtime_id: None = None
    capability: Literal["authority_administrator"] = "authority_administrator"
    assertion_id: str
    identity_provider_id: str
    authentication_method: str
    authentication_assurance: AuthenticationAssurance
    authenticated_at_utc: str
    policy_version: str
    assertion_issued_at_utc: str
    assertion_expires_at_utc: str
    checked_at_utc: str


def require_authority_administration(
    *,
    context: OperatorContext,
    operation: AuthorityAdministrationOperation | str,
    checked_at_utc: str | None = None,
) -> AuthorityAdministrationDecision:
    """Admit one current administration command under the exact policy matrix."""

    required = AUTHORITY_ADMINISTRATION_OPERATION_POLICY.get(operation)  # type: ignore[arg-type]
    effect = AUTHORITY_ADMINISTRATION_OPERATION_EFFECT.get(operation)  # type: ignore[arg-type]
    if required is None or effect is None:
        raise AuthorityAdministrationDeniedError(
            "unknown_authority_administration_operation",
            operation=operation,
        )
    if context.agent_runtime is not None:
        raise AuthorityAdministrationDeniedError(
            "agent_runtime_forbidden",
            operation=operation,
        )
    if context.principal.principal_kind != "human":
        raise AuthorityAdministrationDeniedError(
            "human_principal_required",
            operation=operation,
        )
    assertion = context.authority_administration
    if assertion is None:
        raise AuthorityAdministrationDeniedError(
            "authority_administrator_required",
            operation=operation,
        )
    if assertion.principal_id != context.principal.principal_id:
        raise AuthorityAdministrationDeniedError(
            "assertion_subject_mismatch",
            operation=operation,
        )
    if assertion.provider_id != context.principal.provider_id:
        raise AuthorityAdministrationDeniedError(
            "assertion_provider_mismatch",
            operation=operation,
        )
    if assertion.policy_version != AUTHORITY_ADMINISTRATION_POLICY_VERSION:
        raise AuthorityAdministrationDeniedError(
            "authority_policy_version_mismatch",
            operation=operation,
        )

    checked = _parse_utc(checked_at_utc or datetime.now(UTC).isoformat())
    issued = _parse_utc(assertion.issued_at_utc)
    expires = _parse_utc(assertion.expires_at_utc)
    if checked < issued:
        raise AuthorityAdministrationDeniedError(
            "authority_assertion_not_yet_valid",
            operation=operation,
        )
    if checked >= expires:
        raise AuthorityAdministrationDeniedError(
            "authority_assertion_expired",
            operation=operation,
        )
    if required == "elevated" and assertion.authentication_assurance != "elevated":
        raise AuthorityAdministrationDeniedError(
            "elevated_authentication_required",
            operation=operation,
        )

    return AuthorityAdministrationDecision(
        operation=operation,
        operation_effect=effect,
        required_assurance=required,
        administrator_principal_id=context.principal.principal_id,
        assertion_id=assertion.assertion_id,
        identity_provider_id=context.principal.provider_id,
        authentication_method=context.authentication_method,
        authentication_assurance=assertion.authentication_assurance,
        authenticated_at_utc=context.authenticated_at_utc,
        policy_version=assertion.policy_version,
        assertion_issued_at_utc=assertion.issued_at_utc,
        assertion_expires_at_utc=assertion.expires_at_utc,
        checked_at_utc=checked.isoformat(),
    )


def _parse_utc(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("authority administration timestamp must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("authority administration timestamp must be UTC")
    return parsed.astimezone(UTC)
