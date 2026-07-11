"""Typed operator/account authorization registry for review workflows.

The registry records who may operate a FinHarness review surface. It stores no
credential material and grants no execution authority.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finharness.project_paths import ROOT, display_path

AUTHORIZATION_REGISTRY_ENV_VAR = "FINHARNESS_AUTHORIZATION_REGISTRY_PATH"
DEFAULT_AUTHORIZATION_REGISTRY_PATH = (
    ROOT / "data" / "security" / "authorized-operators.json"
)
AUTHORIZATION_SCHEMA_VERSION = "finharness.authorization_registry.v1"
CREDENTIAL_FIELD_TERMS = ("key", "secret", "token", "password", "private_key")

AuthorizationEnvironment = Literal["paper", "live"]


class AuthorizationRegistryError(RuntimeError):
    """Raised when the authorization registry cannot be trusted."""


class AuthorizedOperator(BaseModel):
    """Human/operator registration without any credential fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operator_id: str
    display_name: str
    scopes: list[str]
    environments: list[AuthorizationEnvironment]

    @field_validator("operator_id", "display_name")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("operator fields must be non-empty")
        return value.strip()


class AuthorizedAccount(BaseModel):
    """Account registration tied to one operator and scope."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: str
    venue: str
    environment: AuthorizationEnvironment
    operator_id: str
    scopes: list[str]

    @field_validator("account_id", "venue", "operator_id")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("account fields must be non-empty")
        return value.strip()


class AuthorizationRegistry(BaseModel):
    """Versioned local registry of operators and accounts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = AUTHORIZATION_SCHEMA_VERSION
    registry_version: str
    updated_at_utc: str
    operators: list[AuthorizedOperator]
    accounts: list[AuthorizedAccount]
    non_claims: list[str] = Field(
        default_factory=lambda: [
            "Registry records review-surface authority only.",
            "Registry stores no credential material.",
            "Registry is not legal authorization.",
            "Registry is not execution authorization.",
        ]
    )


class AuthorizationDecision(BaseModel):
    """Fail-closed authorization decision for one operator/account/scope."""

    model_config = ConfigDict(frozen=True)

    allowed: bool
    operator_id: str
    account_id: str
    environment: AuthorizationEnvironment
    scope: str
    registry_version: str | None = None
    registry_ref: str | None = None
    reason: str
    blocking_reasons: list[str] = Field(default_factory=list)
    non_claims: list[str] = Field(
        default_factory=lambda: [
            "Not legal authorization.",
            "Not execution authorization.",
            "No credential material is stored.",
        ]
    )
    execution_allowed: Literal[False] = False


def authorization_registry_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    env_path = os.environ.get(AUTHORIZATION_REGISTRY_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_AUTHORIZATION_REGISTRY_PATH


def credential_field_hits(value: Any, *, prefix: str = "$") -> list[str]:
    """Return paths whose field names look like credential material."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            child_prefix = f"{prefix}.{key}"
            if any(term in normalized for term in CREDENTIAL_FIELD_TERMS):
                hits.append(child_prefix)
            hits.extend(credential_field_hits(child, prefix=child_prefix))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(credential_field_hits(child, prefix=f"{prefix}[{index}]"))
    return hits


def load_authorization_registry(path: str | Path | None = None) -> AuthorizationRegistry:
    """Load the local authorization registry; unreadable input fails closed."""
    target = authorization_registry_path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthorizationRegistryError(
            f"authorization registry unreadable: {target}: {exc}"
        ) from exc
    hits = credential_field_hits(payload)
    if hits:
        raise AuthorizationRegistryError(
            "authorization registry contains forbidden credential-like fields: "
            + ", ".join(hits)
        )
    try:
        return AuthorizationRegistry.model_validate(payload)
    except ValueError as exc:
        raise AuthorizationRegistryError(
            f"authorization registry invalid: {target}: {exc}"
        ) from exc


def _fail_decision(
    *,
    operator_id: str,
    account_id: str,
    environment: AuthorizationEnvironment,
    scope: str,
    reason: str,
    registry_ref: str | None,
    registry_version: str | None = None,
) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=False,
        operator_id=operator_id,
        account_id=account_id,
        environment=environment,
        scope=scope,
        registry_version=registry_version,
        registry_ref=registry_ref,
        reason=reason,
        blocking_reasons=[reason],
        execution_allowed=False,
    )


def authorize(
    *,
    operator_id: str,
    account_id: str,
    environment: AuthorizationEnvironment,
    scope: str,
    registry: AuthorizationRegistry | None = None,
    registry_path: str | Path | None = None,
) -> AuthorizationDecision:
    """Evaluate one operator/account/scope request without side effects."""
    target = authorization_registry_path(registry_path)
    registry_ref = display_path(target)
    try:
        active_registry = registry or load_authorization_registry(target)
    except AuthorizationRegistryError as exc:
        return _fail_decision(
            operator_id=operator_id,
            account_id=account_id,
            environment=environment,
            scope=scope,
            reason=str(exc),
            registry_ref=registry_ref,
        )

    operator = next(
        (item for item in active_registry.operators if item.operator_id == operator_id),
        None,
    )
    if operator is None:
        return _fail_decision(
            operator_id=operator_id,
            account_id=account_id,
            environment=environment,
            scope=scope,
            registry_version=active_registry.registry_version,
            registry_ref=registry_ref,
            reason=f"operator is not registered: {operator_id}",
        )
    if environment not in operator.environments:
        return _fail_decision(
            operator_id=operator_id,
            account_id=account_id,
            environment=environment,
            scope=scope,
            registry_version=active_registry.registry_version,
            registry_ref=registry_ref,
            reason=f"operator {operator_id} is not registered for environment {environment}",
        )
    if scope not in operator.scopes:
        return _fail_decision(
            operator_id=operator_id,
            account_id=account_id,
            environment=environment,
            scope=scope,
            registry_version=active_registry.registry_version,
            registry_ref=registry_ref,
            reason=f"operator {operator_id} is not registered for scope {scope}",
        )

    account = next(
        (
            item
            for item in active_registry.accounts
            if item.account_id == account_id and item.environment == environment
        ),
        None,
    )
    if account is None:
        return _fail_decision(
            operator_id=operator_id,
            account_id=account_id,
            environment=environment,
            scope=scope,
            registry_version=active_registry.registry_version,
            registry_ref=registry_ref,
            reason=f"account is not registered for environment: {account_id}/{environment}",
        )
    if account.operator_id != operator_id:
        return _fail_decision(
            operator_id=operator_id,
            account_id=account_id,
            environment=environment,
            scope=scope,
            registry_version=active_registry.registry_version,
            registry_ref=registry_ref,
            reason=(
                f"account {account_id} belongs to operator {account.operator_id}, "
                f"not {operator_id}"
            ),
        )
    if scope not in account.scopes:
        return _fail_decision(
            operator_id=operator_id,
            account_id=account_id,
            environment=environment,
            scope=scope,
            registry_version=active_registry.registry_version,
            registry_ref=registry_ref,
            reason=f"account {account_id} is not registered for scope {scope}",
        )

    return AuthorizationDecision(
        allowed=True,
        operator_id=operator_id,
        account_id=account_id,
        environment=environment,
        scope=scope,
        registry_version=active_registry.registry_version,
        registry_ref=registry_ref,
        reason="registered operator/account/scope/environment matched",
        blocking_reasons=[],
        execution_allowed=False,
    )
