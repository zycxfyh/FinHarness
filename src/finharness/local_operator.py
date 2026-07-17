"""Local write capability gate for the FinHarness API.

This module provides a fail-closed write capability boundary. The API is
read-only by default. State-changing operations require an explicit
local operator context passed at application creation time.

This compatibility adapter mints an explicitly unverified legacy provenance
label into the authenticated identity boundary. Production callers should pass
an IdentityProvider to create_app instead.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Request

from finharness.identity import OperatorContext, PrincipalIdentity, StaticIdentityProvider


class LocalOperatorContext:
    """A local operator identity for capability gating.

    This is a simple process-level label, not a user session or auth token.
    It exists to make the write capability boundary explicit and auditable.

    Attributes:
        operator_id: A human-readable label for the current operator
            (e.g. ``"local_operator"``, ``"admin_cli"``, ``"test_harness"``).
    """

    def __init__(self, operator_id: str) -> None:
        if not operator_id or not operator_id.strip():
            raise ValueError("operator_id must be a non-empty string")
        self.operator_id = operator_id.strip()

    def identity_provider(self) -> StaticIdentityProvider:
        principal_id = f"legacy-local:{self.operator_id}"
        return StaticIdentityProvider(
            OperatorContext(
                principal=PrincipalIdentity(
                    principal_id=principal_id,
                    provider_id="legacy-local",
                    principal_kind="legacy_unknown",
                    display_label=self.operator_id,
                    legacy_label=self.operator_id,
                    legacy_label_verified=False,
                ),
                authentication_method="legacy_local_process_context",
                authenticated_at_utc=datetime.now(UTC).isoformat(),
            )
        )


async def require_write_capability(request: Request) -> OperatorContext:
    """FastAPI dependency that fails closed.

    Returns the active :class:`LocalOperatorContext` if one was passed to
    :func:`create_app`. Raises ``HTTPException(403)`` if writes are not
    explicitly enabled for this application instance.

    This dependency must be added to every state-changing route handler.
    GET routes and validation-only POST routes must NOT use it.
    """
    from finharness.identity import require_authenticated_operator

    return await require_authenticated_operator(request)
