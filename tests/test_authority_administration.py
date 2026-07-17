from __future__ import annotations

import unittest

from pydantic import ValidationError

from finharness.authority_administration import (
    AUTHORITY_ADMINISTRATION_OPERATION_POLICY,
    AUTHORITY_ADMINISTRATION_POLICY_VERSION,
    AuthorityAdministrationDeniedError,
    require_authority_administration,
)
from finharness.identity import (
    AgentRuntimeIdentity,
    AuthorityAdministrationAssertion,
    OperatorContext,
    PrincipalIdentity,
)

CHECKED_AT = "2026-07-17T08:00:00+00:00"


def operator_context(
    *,
    principal_kind: str = "human",
    assurance: str = "elevated",
    admin: bool = True,
    agent_runtime: bool = False,
    policy_version: str = AUTHORITY_ADMINISTRATION_POLICY_VERSION,
    issued_at_utc: str = "2026-07-17T07:00:00+00:00",
    expires_at_utc: str = "2026-07-17T09:00:00+00:00",
) -> OperatorContext:
    principal = PrincipalIdentity.model_validate(
        {
            "principal_id": "principal:alice",
            "provider_id": "test-provider",
            "principal_kind": principal_kind,
        }
    )
    assertion = (
        AuthorityAdministrationAssertion.model_validate(
            {
                "assertion_id": "assertion:alice:1",
                "principal_id": principal.principal_id,
                "provider_id": principal.provider_id,
                "capability": "authority_administrator",
                "policy_version": policy_version,
                "authentication_assurance": assurance,
                "issued_at_utc": issued_at_utc,
                "expires_at_utc": expires_at_utc,
            }
        )
        if admin
        else None
    )
    runtime = (
        AgentRuntimeIdentity(
            agent_runtime_id="runtime:alice-agent",
            principal_id=principal.principal_id,
            provider_id=principal.provider_id,
        )
        if agent_runtime
        else None
    )
    return OperatorContext(
        principal=principal,
        agent_runtime=runtime,
        authority_administration=assertion,
        authentication_method="test-bearer",
        authenticated_at_utc=CHECKED_AT,
    )


class AuthorityAdministrationTests(unittest.TestCase):
    def test_exact_operation_matrix(self) -> None:
        self.assertEqual(
            AUTHORITY_ADMINISTRATION_OPERATION_POLICY,
            {
                "mandate_create_or_replace": "elevated",
                "mandate_resume": "elevated",
                "mandate_suspend": "standard",
                "mandate_revoke": "standard",
                "grant_create": "elevated",
                "grant_revoke": "standard",
            },
        )

    def test_elevated_human_admin_is_admitted_for_every_operation(self) -> None:
        context = operator_context()
        for operation, required in AUTHORITY_ADMINISTRATION_OPERATION_POLICY.items():
            with self.subTest(operation=operation):
                decision = require_authority_administration(
                    context=context,
                    operation=operation,
                    checked_at_utc=CHECKED_AT,
                )
                self.assertTrue(decision.admitted)
                self.assertEqual(decision.required_assurance, required)
                self.assertEqual(decision.administrator_principal_id, "principal:alice")
                self.assertIsNone(decision.agent_runtime_id)

    def test_standard_human_admin_only_reduces_authority(self) -> None:
        context = operator_context(assurance="standard")
        for operation, required in AUTHORITY_ADMINISTRATION_OPERATION_POLICY.items():
            with self.subTest(operation=operation):
                if required == "elevated":
                    with self.assertRaisesRegex(
                        AuthorityAdministrationDeniedError,
                        "elevated_authentication_required",
                    ):
                        require_authority_administration(
                            context=context,
                            operation=operation,
                            checked_at_utc=CHECKED_AT,
                        )
                else:
                    require_authority_administration(
                        context=context,
                        operation=operation,
                        checked_at_utc=CHECKED_AT,
                    )

    def test_agent_under_admin_principal_is_denied(self) -> None:
        with self.assertRaisesRegex(
            AuthorityAdministrationDeniedError,
            "agent_runtime_forbidden",
        ):
            require_authority_administration(
                context=operator_context(agent_runtime=True),
                operation="mandate_suspend",
                checked_at_utc=CHECKED_AT,
            )

    def test_non_human_principals_are_denied(self) -> None:
        for kind in ("service", "legacy_unknown"):
            with self.subTest(kind=kind), self.assertRaisesRegex(
                AuthorityAdministrationDeniedError,
                "human_principal_required",
            ):
                require_authority_administration(
                    context=operator_context(principal_kind=kind),
                    operation="mandate_suspend",
                    checked_at_utc=CHECKED_AT,
                )

    def test_ordinary_human_is_denied(self) -> None:
        with self.assertRaisesRegex(
            AuthorityAdministrationDeniedError,
            "authority_administrator_required",
        ):
            require_authority_administration(
                context=operator_context(admin=False),
                operation="grant_revoke",
                checked_at_utc=CHECKED_AT,
            )

    def test_assertion_currentness_and_policy_are_fail_closed(self) -> None:
        cases = (
            (
                operator_context(issued_at_utc="2026-07-17T08:00:01+00:00"),
                "authority_assertion_not_yet_valid",
            ),
            (
                operator_context(expires_at_utc=CHECKED_AT),
                "authority_assertion_expired",
            ),
            (
                operator_context(policy_version="finharness.authority-administration.v0"),
                "authority_policy_version_mismatch",
            ),
        )
        for context, reason in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(
                AuthorityAdministrationDeniedError,
                reason,
            ):
                require_authority_administration(
                    context=context,
                    operation="mandate_create_or_replace",
                    checked_at_utc=CHECKED_AT,
                )

    def test_unknown_operation_is_denied(self) -> None:
        with self.assertRaisesRegex(
            AuthorityAdministrationDeniedError,
            "unknown_authority_administration_operation",
        ):
            require_authority_administration(
                context=operator_context(),
                operation="mandate_expand",
                checked_at_utc=CHECKED_AT,
            )

    def test_identity_models_forbid_parallel_authority_fields(self) -> None:
        cases = (
            (
                PrincipalIdentity,
                {
                    "principal_id": "principal:alice",
                    "provider_id": "test-provider",
                    "principal_kind": "human",
                    "is_admin": True,
                },
            ),
            (
                AuthorityAdministrationAssertion,
                {
                    "assertion_id": "assertion:alice:1",
                    "principal_id": "principal:alice",
                    "provider_id": "test-provider",
                    "capability": "authority_administrator",
                    "policy_version": AUTHORITY_ADMINISTRATION_POLICY_VERSION,
                    "authentication_assurance": "elevated",
                    "issued_at_utc": "2026-07-17T07:00:00+00:00",
                    "expires_at_utc": "2026-07-17T09:00:00+00:00",
                    "aal": "aal2",
                },
            ),
            (
                OperatorContext,
                {
                    **operator_context().model_dump(mode="json"),
                    "authority_admin_v2": True,
                },
            ),
        )
        for model, payload in cases:
            with self.subTest(model=model.__name__), self.assertRaises(ValidationError):
                model.model_validate(payload)

    def test_assertion_subject_and_provider_are_bound_at_construction(self) -> None:
        base = operator_context().model_dump(mode="json")
        for field, value, reason in (
            ("principal_id", "principal:bob", "principal binding mismatch"),
            ("provider_id", "other-provider", "provider binding mismatch"),
        ):
            payload = dict(base)
            assertion = dict(payload["authority_administration"])
            assertion[field] = value
            payload["authority_administration"] = assertion
            with self.subTest(field=field), self.assertRaisesRegex(ValidationError, reason):
                OperatorContext.model_validate(payload)

    def test_assertion_timestamps_are_closed_utc_interval(self) -> None:
        base = operator_context().authority_administration
        assert base is not None
        payload = base.model_dump(mode="json")
        for updates, reason in (
            ({"issued_at_utc": "not-a-time"}, "ISO-8601"),
            ({"expires_at_utc": "2026-07-17T09:00:00"}, "must be UTC"),
            (
                {
                    "issued_at_utc": "2026-07-17T09:00:00+00:00",
                    "expires_at_utc": "2026-07-17T09:00:00+00:00",
                },
                "expiry must follow issuance",
            ),
        ):
            with self.subTest(updates=updates), self.assertRaisesRegex(
                ValidationError,
                reason,
            ):
                AuthorityAdministrationAssertion.model_validate(payload | updates)


if __name__ == "__main__":
    unittest.main()
