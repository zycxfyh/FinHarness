"""Authenticated actor identities and provider-neutral operator context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator


class PrincipalIdentity(BaseModel):
    """Stable authenticated human/service principal; never capital authority."""

    model_config = ConfigDict(frozen=True)

    principal_id: str
    provider_id: str
    display_label: str | None = None
    legacy_label: str | None = None
    legacy_label_verified: bool = False

    @field_validator("principal_id", "provider_id")
    @classmethod
    def require_stable_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identity ids must be non-empty")
        return value.strip()


class AgentRuntimeIdentity(BaseModel):
    """Authenticated runtime instance bound to exactly one principal."""

    model_config = ConfigDict(frozen=True)

    agent_runtime_id: str
    principal_id: str
    provider_id: str
    agent_profile: str | None = None

    @field_validator("agent_runtime_id", "principal_id", "provider_id")
    @classmethod
    def require_stable_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identity ids must be non-empty")
        return value.strip()


class IdentitySubstitutionError(ValueError):
    """Raised when request-supplied identity differs from authenticated context."""


class OperatorContext(BaseModel):
    """Server-authenticated actor context, intentionally separate from authority."""

    model_config = ConfigDict(frozen=True)

    principal: PrincipalIdentity
    agent_runtime: AgentRuntimeIdentity | None = None
    authentication_method: str
    authenticated_at_utc: str

    def model_post_init(self, _context: object) -> None:
        if (
            self.agent_runtime is not None
            and self.agent_runtime.principal_id != self.principal.principal_id
        ):
            raise ValueError("agent runtime principal binding mismatch")

    @property
    def operator_id(self) -> str:
        """Compatibility alias for callers that only need the stable principal id."""

        return self.principal.principal_id

    def reject_identity_substitution(
        self,
        *,
        claimed_principal_id: str | None = None,
        claimed_agent_runtime_id: str | None = None,
    ) -> None:
        if claimed_principal_id and claimed_principal_id != self.principal.principal_id:
            raise IdentitySubstitutionError("cross-principal substitution denied")
        actual_agent = self.agent_runtime.agent_runtime_id if self.agent_runtime else None
        if claimed_agent_runtime_id and claimed_agent_runtime_id != actual_agent:
            raise IdentitySubstitutionError("cross-agent substitution denied")

    def receipt_binding(self) -> dict[str, object]:
        return {
            "principal_id": self.principal.principal_id,
            "agent_runtime_id": (
                self.agent_runtime.agent_runtime_id if self.agent_runtime is not None else None
            ),
            "identity_provider_id": self.principal.provider_id,
            "authentication_method": self.authentication_method,
            "capital_authority": None,
            "legacy_actor_label": self.principal.legacy_label,
            "legacy_actor_label_verified": self.principal.legacy_label_verified,
        }


@runtime_checkable
class IdentityProvider(Protocol):
    """Port implemented by production authentication and deterministic test providers."""

    async def authenticate(self, request: Request) -> OperatorContext | None: ...


@dataclass(frozen=True)
class TestIdentityProvider:
    """Deterministic provider for integration fixtures; tokens never enter payloads."""

    identities_by_token: dict[str, OperatorContext]

    async def authenticate(self, request: Request) -> OperatorContext | None:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        return self.identities_by_token.get(token)


@dataclass(frozen=True)
class StaticIdentityProvider:
    """Process-bound provider used by the explicit local compatibility adapter."""

    context: OperatorContext

    async def authenticate(self, _request: Request) -> OperatorContext:
        return self.context


async def require_authenticated_operator(request: Request) -> OperatorContext:
    provider = getattr(request.app.state, "identity_provider", None)
    if not isinstance(provider, IdentityProvider):
        raise _authentication_required()
    context = await provider.authenticate(request)
    if context is None:
        raise _authentication_required()
    request.state.operator_context = context
    return context


def _authentication_required() -> HTTPException:
    return HTTPException(
        status_code=403,
        detail={
            "code": "write_capability_required",
            "message": "Governed writes require a server-authenticated operator context.",
            "execution_allowed": False,
            "authority_transition": False,
        },
    )


def write_identity_receipt(
    root: Path,
    *,
    context: OperatorContext,
    method: str,
    path: str,
    trace_id: str,
    status_code: int,
) -> Path:
    """Persist an immutable identity binding for a governed HTTP write."""

    root.mkdir(parents=True, exist_ok=True)
    receipt_id = f"identity_receipt_{uuid4().hex}"
    payload = {
        "schema": "finharness.authenticated_actor_receipt.v1",
        "receipt_id": receipt_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "request": {"method": method, "path": path, "trace_id": trace_id},
        "response_status_code": status_code,
        "actor": context.receipt_binding(),
        "non_claims": [
            "Authentication identity is not capital authority.",
            "This receipt does not authorize execution.",
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["content_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    target = root / f"{receipt_id}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
