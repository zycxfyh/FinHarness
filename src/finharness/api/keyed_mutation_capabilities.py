"""Closed route-capability contract for the authenticated keyed-mutation protocol."""

from __future__ import annotations

import json
from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)
from starlette.routing import Match

from finharness.project_paths import ROOT
from finharness.statecore.receipt_io import canonical_json_sha256

REGISTRY_SCHEMA = "finharness.keyed_mutation_route_capability_registry.v1"
DEFAULT_REGISTRY_PATH = ROOT / "config" / "keyed-mutation-route-capabilities.json"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class KeyedMutationCapabilityError(RuntimeError):
    """Raised when the canonical registry or runtime route graph violates #387."""


class KeyedMutationRouteMode(StrEnum):
    TYPED_DOMAIN_RECONCILIATION = "typed_domain_reconciliation"
    TERMINAL_REPLAY_ONLY = "terminal_replay_only"
    KEYED_MUTATION_PROHIBITED = "keyed_mutation_prohibited"


class KeyedMutationRouteCapability(BaseModel):
    """One immutable, versioned route recovery capability."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_id: str
    registry_version: str
    method: str
    canonical_path_template: str
    mode: KeyedMutationRouteMode
    owning_domain: str
    request_identity_policy_id: str
    max_request_bytes: int
    max_response_bytes: int
    resolver_id: str | None
    no_ambiguous_effect_contract: str | None
    execution_allowed: bool

    @field_validator(
        "capability_id",
        "registry_version",
        "canonical_path_template",
        "owning_domain",
        "request_identity_policy_id",
    )
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("route capability string fields must be non-empty")
        return value.strip()

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        method = value.strip().upper()
        if not method or method in SAFE_METHODS:
            raise ValueError("route capability method must be non-safe")
        return method

    @field_validator("max_request_bytes", "max_response_bytes")
    @classmethod
    def require_positive_bound(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("route capability bounds must be positive")
        return value

    @model_validator(mode="after")
    def require_mode_contract(self) -> KeyedMutationRouteCapability:
        if self.execution_allowed:
            raise ValueError("route recovery capability never grants execution authority")
        if self.mode is KeyedMutationRouteMode.TYPED_DOMAIN_RECONCILIATION:
            if not self.resolver_id or not self.resolver_id.strip():
                raise ValueError("typed route capability requires resolver_id")
            if self.no_ambiguous_effect_contract is not None:
                raise ValueError("typed route capability cannot declare terminal-only proof")
        elif self.mode is KeyedMutationRouteMode.TERMINAL_REPLAY_ONLY:
            if self.resolver_id is not None:
                raise ValueError("terminal-only route capability cannot declare resolver_id")
            if (
                self.no_ambiguous_effect_contract is None
                or not self.no_ambiguous_effect_contract.strip()
            ):
                raise ValueError("terminal-only route capability requires no-ambiguity proof")
        else:
            if self.resolver_id is not None:
                raise ValueError("prohibited route capability cannot declare resolver_id")
            if self.no_ambiguous_effect_contract is not None:
                raise ValueError("prohibited route capability cannot declare terminal-only proof")
        return self

    @property
    def capability_sha256(self) -> str:
        return canonical_json_sha256(self.model_dump(mode="json"))

    def receipt_binding(self) -> dict[str, Any]:
        return self.model_dump(mode="json") | {
            "capability_sha256": self.capability_sha256,
        }


class KeyedMutationRouteCapabilityRegistry(BaseModel):
    """The single runtime and audit data owner."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_id: str = Field(alias="schema", serialization_alias="schema")
    registry_version: str
    capabilities: tuple[KeyedMutationRouteCapability, ...]

    @model_validator(mode="after")
    def require_closed_registry(self) -> KeyedMutationRouteCapabilityRegistry:
        if self.schema_id != REGISTRY_SCHEMA:
            raise ValueError("keyed-mutation capability registry schema is invalid")
        if not self.registry_version.strip():
            raise ValueError("keyed-mutation capability registry version is missing")
        ids: set[str] = set()
        routes: set[tuple[str, str]] = set()
        for capability in self.capabilities:
            if capability.registry_version != self.registry_version:
                raise ValueError(
                    f"{capability.capability_id}: registry_version differs from registry"
                )
            if capability.capability_id in ids:
                raise ValueError(f"duplicate capability_id: {capability.capability_id}")
            route_key = (capability.method, capability.canonical_path_template)
            if route_key in routes:
                raise ValueError(f"duplicate route capability: {route_key[0]} {route_key[1]}")
            ids.add(capability.capability_id)
            routes.add(route_key)
        return self

    def by_route(self, method: str, path_template: str) -> KeyedMutationRouteCapability | None:
        key = (method.upper(), path_template)
        return next(
            (
                capability
                for capability in self.capabilities
                if (capability.method, capability.canonical_path_template) == key
            ),
            None,
        )

    def by_id(self, capability_id: str) -> KeyedMutationRouteCapability | None:
        return next(
            (
                capability
                for capability in self.capabilities
                if capability.capability_id == capability_id
            ),
            None,
        )

    @property
    def typed_resolver_ids(self) -> frozenset[str]:
        return frozenset(
            capability.resolver_id
            for capability in self.capabilities
            if capability.mode is KeyedMutationRouteMode.TYPED_DOMAIN_RECONCILIATION
            and capability.resolver_id is not None
        )


def load_keyed_mutation_route_capabilities(
    path: str | Path = DEFAULT_REGISTRY_PATH,
) -> KeyedMutationRouteCapabilityRegistry:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return KeyedMutationRouteCapabilityRegistry.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise KeyedMutationCapabilityError(
            f"invalid keyed-mutation capability registry: {exc}"
        ) from exc


@dataclass(frozen=True)
class MatchedApiRoute:
    method: str
    canonical_path_template: str
    path_params: dict[str, str]


def _route_contexts(api: FastAPI) -> Iterable[Any]:
    """Yield effective APIRoute contexts across FastAPI 0.137 router trees."""

    for route in api.routes:
        if isinstance(route, APIRoute):
            yield route
            continue
        effective = getattr(route, "effective_route_contexts", None)
        if callable(effective):
            yield from effective()


def actual_non_safe_api_routes(api: FastAPI) -> frozenset[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in _route_contexts(api):
        path_template = getattr(route, "path_format", None) or getattr(route, "path", None)
        if not isinstance(path_template, str):
            continue
        for method in getattr(route, "methods", set()) or set():
            if method not in SAFE_METHODS:
                routes.add((method, path_template))
    return frozenset(routes)


def match_api_route(
    api: FastAPI,
    scope: MutableMapping[str, Any],
) -> MatchedApiRoute | None:
    """Resolve exactly one effective APIRoute using its Starlette matcher."""

    matches: list[MatchedApiRoute] = []
    method = str(scope.get("method", "")).upper()
    for route in _route_contexts(api):
        match, child_scope = route.matches(scope)
        if match is not Match.FULL:
            continue
        path_template = getattr(route, "path_format", None) or getattr(route, "path", None)
        if not isinstance(path_template, str):
            continue
        path_params = child_scope.get("path_params", {})
        matches.append(
            MatchedApiRoute(
                method=method,
                canonical_path_template=path_template,
                path_params={
                    str(key): str(value)
                    for key, value in path_params.items()
                },
            )
        )
    if not matches:
        return None
    if len(matches) != 1:
        identities = sorted(
            f"{match.method} {match.canonical_path_template}" for match in matches
        )
        raise KeyedMutationCapabilityError(
            "ambiguous FastAPI route match: " + ", ".join(identities)
        )
    return matches[0]


def audit_keyed_mutation_route_capabilities(
    api: FastAPI,
    registry: KeyedMutationRouteCapabilityRegistry,
    *,
    dispatcher_resolver_ids: frozenset[str],
) -> dict[str, Any]:
    actual = actual_non_safe_api_routes(api)
    declared = frozenset(
        (capability.method, capability.canonical_path_template)
        for capability in registry.capabilities
    )
    missing = sorted(actual - declared)
    stale = sorted(declared - actual)
    if missing or stale:
        findings = [
            *(f"missing registry entry: {method} {path}" for method, path in missing),
            *(f"registry entry has no APIRoute: {method} {path}" for method, path in stale),
        ]
        raise KeyedMutationCapabilityError("; ".join(findings))
    if registry.typed_resolver_ids != dispatcher_resolver_ids:
        missing_dispatch = sorted(registry.typed_resolver_ids - dispatcher_resolver_ids)
        extra_dispatch = sorted(dispatcher_resolver_ids - registry.typed_resolver_ids)
        raise KeyedMutationCapabilityError(
            "registry/dispatcher resolver drift: "
            f"missing={missing_dispatch}, extra={extra_dispatch}"
        )
    modes = {
        mode.value: sum(1 for capability in registry.capabilities if capability.mode is mode)
        for mode in KeyedMutationRouteMode
    }
    return {
        "ok": True,
        "schema": registry.schema_id,
        "registry_version": registry.registry_version,
        "non_safe_route_count": len(actual),
        "mode_counts": modes,
        "typed_resolver_ids": sorted(registry.typed_resolver_ids),
        "routes": [
            {
                "method": capability.method,
                "canonical_path_template": capability.canonical_path_template,
                "capability_id": capability.capability_id,
                "capability_sha256": capability.capability_sha256,
                "mode": capability.mode.value,
                "resolver_id": capability.resolver_id,
            }
            for capability in registry.capabilities
        ],
        "execution_allowed": False,
    }
