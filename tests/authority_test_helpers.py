from __future__ import annotations

from finharness.authority_administration import AUTHORITY_ADMINISTRATION_POLICY_VERSION
from finharness.identity import (
    AgentRuntimeIdentity,
    AuthorityAdministrationAssertion,
    OperatorContext,
    PrincipalIdentity,
)


def authority_admin_context(
    principal_id: str = "principal:test-admin",
    *,
    provider_id: str = "test-authority-provider",
    assurance: str = "elevated",
    principal_kind: str = "human",
    legacy_label: str | None = None,
    with_assertion: bool = True,
    agent_runtime_id: str | None = None,
    policy_version: str = AUTHORITY_ADMINISTRATION_POLICY_VERSION,
    issued_at_utc: str = "2000-01-01T00:00:00+00:00",
    expires_at_utc: str = "2100-01-01T00:00:00+00:00",
) -> OperatorContext:
    principal = PrincipalIdentity.model_validate(
        {
            "principal_id": principal_id,
            "provider_id": provider_id,
            "principal_kind": principal_kind,
            "legacy_label": legacy_label,
            "legacy_label_verified": False,
        }
    )
    assertion = (
        AuthorityAdministrationAssertion.model_validate(
            {
                "assertion_id": f"assertion:{principal_id}",
                "principal_id": principal_id,
                "provider_id": provider_id,
                "capability": "authority_administrator",
                "policy_version": policy_version,
                "authentication_assurance": assurance,
                "issued_at_utc": issued_at_utc,
                "expires_at_utc": expires_at_utc,
            }
        )
        if with_assertion
        else None
    )
    runtime = (
        AgentRuntimeIdentity(
            agent_runtime_id=agent_runtime_id,
            principal_id=principal_id,
            provider_id=provider_id,
        )
        if agent_runtime_id is not None
        else None
    )
    return OperatorContext(
        principal=principal,
        agent_runtime=runtime,
        authority_administration=assertion,
        authentication_method="test-bearer",
        authenticated_at_utc="2026-07-17T00:00:00+00:00",
    )
