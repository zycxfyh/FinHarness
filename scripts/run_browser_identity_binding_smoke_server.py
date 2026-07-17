#!/usr/bin/env python3
"""Real-browser fixture for authenticated mutation-attempt identity binding."""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from finharness.api.app import create_app
from finharness.identity import OperatorContext, PrincipalIdentity, TestIdentityProvider
from finharness.statecore.store import init_state_core


def _identity(
    principal_id: str,
    epoch_id: str,
    *,
    expires_at_utc: str = "2099-01-01T00:00:00+00:00",
) -> OperatorContext:
    return OperatorContext(
        principal=PrincipalIdentity(
            principal_id=principal_id,
            provider_id="browser-smoke-provider",
            principal_kind="human",
        ),
        authentication_method="test_bearer",
        authenticated_at_utc="2026-01-01T00:00:00+00:00",
        authentication_epoch_id=epoch_id,
        authentication_expires_at_utc=expires_at_utc,
    )


def main() -> None:
    root = Path(os.environ["BROWSER_IDENTITY_BINDING_ROOT"])
    root.mkdir(parents=True, exist_ok=True)
    provider = TestIdentityProvider(
        {
            "alice-session-1": _identity("principal:alice", "alice-session-1"),
            "alice-session-2": _identity("principal:alice", "alice-session-2"),
            "bob-session-1": _identity("principal:bob", "bob-session-1"),
            "expired-alice-session": _identity(
                "principal:alice",
                "expired-alice-session",
                expires_at_utc="2026-01-02T00:00:00+00:00",
            ),
        }
    )
    app = create_app(
        state_core_engine=init_state_core(root / "state.sqlite"),
        receipt_root=str(root / "receipts"),
        identity_provider=provider,
    )
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("BROWSER_IDENTITY_BINDING_PORT", "8788")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
