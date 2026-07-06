"""Local write capability gate for the FinHarness API.

This module provides a fail-closed write capability boundary. The API is
read-only by default. State-changing operations require an explicit
local operator context passed at application creation time.

This is a local process capability boundary, not external authentication.
It does not provide OAuth, JWT, RBAC, session management, or broker
authorization.
"""

from __future__ import annotations

from fastapi import HTTPException, Request


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


async def require_write_capability(request: Request) -> LocalOperatorContext:
    """FastAPI dependency that fails closed.

    Returns the active :class:`LocalOperatorContext` if one was passed to
    :func:`create_app`. Raises ``HTTPException(403)`` if writes are not
    explicitly enabled for this application instance.

    This dependency must be added to every state-changing route handler.
    GET routes and validation-only POST routes must NOT use it.
    """
    ctx = getattr(request.app.state, "local_operator_context", None)
    if not isinstance(ctx, LocalOperatorContext):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "write_capability_required",
                "message": (
                    "Local writes are not enabled for this application instance. "
                    "Pass local_operator_context to create_app() to enable governed writes."
                ),
                "execution_allowed": False,
                "authority_transition": False,
            },
        )
    return ctx
