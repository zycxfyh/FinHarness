"""Domain-neutral registry and dispatcher for typed identity-mutation recovery."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from starlette.routing import compile_path

from finharness.api.keyed_mutation_capabilities import (
    IdentityMutationResolverContract,
    KeyedMutationCapabilityError,
    KeyedMutationRouteMode,
    identity_mutation_resolver_contract_maps,
    load_keyed_mutation_route_capabilities,
)
from finharness.identity import (
    IdentityMutationError,
    load_identity_mutation_receipt,
)


def identity_mutation_reconciliation_contracts() -> tuple[IdentityMutationResolverContract, ...]:
    """Return every typed resolver contract without making one route domain the registry owner."""

    from finharness.api.routes_agent_shell import (
        agent_shell_identity_mutation_reconciliation_contracts,
    )
    from finharness.api.routes_proposals import (
        proposal_identity_mutation_reconciliation_contracts,
    )

    return (
        *proposal_identity_mutation_reconciliation_contracts(),
        *agent_shell_identity_mutation_reconciliation_contracts(),
    )


def _contract_maps() -> tuple[
    dict[tuple[str, str], IdentityMutationResolverContract],
    dict[str, IdentityMutationResolverContract],
]:
    try:
        return identity_mutation_resolver_contract_maps(
            identity_mutation_reconciliation_contracts()
        )
    except KeyedMutationCapabilityError as exc:
        raise IdentityMutationError(str(exc)) from exc


def _v2_route_resolution(
    mutation: dict[str, Any],
    *,
    method: str,
    path: str,
) -> tuple[str, str | None]:
    binding = mutation.get("route_capability")
    if not isinstance(binding, dict):
        raise IdentityMutationError("mutation route capability binding is missing")
    capability_id = binding.get("capability_id")
    if not isinstance(capability_id, str):
        raise IdentityMutationError("mutation route capability id is missing")
    capability = load_keyed_mutation_route_capabilities().by_id(capability_id)
    if capability is None or binding != capability.receipt_binding():
        raise IdentityMutationError(
            "mutation route capability does not match the canonical registry"
        )
    if (
        capability.mode is not KeyedMutationRouteMode.TYPED_DOMAIN_RECONCILIATION
        or capability.resolver_id is None
    ):
        raise IdentityMutationError(
            "mutation route capability has no typed reconciliation resolver"
        )
    if method != capability.method:
        raise IdentityMutationError("mutation method differs from route capability")
    route_regex, _path_format, _convertors = compile_path(capability.canonical_path_template)
    matched = route_regex.fullmatch(path)
    if matched is None:
        raise IdentityMutationError("mutation path differs from route capability")
    return capability.resolver_id, matched.groupdict().get("proposal_id")


def _v1_route_resolution(*, method: str, path: str) -> tuple[str, str | None]:
    by_route, _by_resolver = _contract_maps()
    matches: list[tuple[IdentityMutationResolverContract, str | None]] = []
    for contract in by_route.values():
        if contract.method != method:
            continue
        route_regex, _path_format, _convertors = compile_path(contract.canonical_path_template)
        matched = route_regex.fullmatch(path)
        if matched is not None:
            matches.append((contract, matched.groupdict().get("proposal_id")))
    if len(matches) != 1:
        raise IdentityMutationError(
            "no unique typed reconciliation resolver for this legacy mutation route"
        )
    contract, proposal_id = matches[0]
    return contract.resolver_id, proposal_id


def mutation_route_resolution(
    mutation: dict[str, Any],
    *,
    method: str,
    path: str,
) -> tuple[str, str | None]:
    schema = mutation.get("schema")
    if schema == "finharness.api_mutation_identity_receipt.v2":
        return _v2_route_resolution(mutation, method=method, path=path)
    if schema == "finharness.api_mutation_identity_receipt.v1":
        return _v1_route_resolution(method=method, path=path)
    raise IdentityMutationError("unsupported mutation receipt schema")


def require_pending_identity_mutation_route(
    mutation: dict[str, Any],
) -> tuple[str, dict[str, Any], str, str | None]:
    if mutation.get("state") != "pending":
        raise IdentityMutationError("only a pending mutation can be reconciled")
    receipt_id = mutation.get("receipt_id")
    request_binding = mutation.get("request")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise IdentityMutationError("mutation receipt id is missing")
    if not isinstance(request_binding, dict):
        raise IdentityMutationError("mutation receipt request binding is missing")
    method = request_binding.get("method")
    path = request_binding.get("path")
    if not isinstance(method, str):
        raise IdentityMutationError("mutation request method is missing")
    if not isinstance(path, str):
        raise IdentityMutationError("mutation request path is missing")
    resolver_id, proposal_id = mutation_route_resolution(
        mutation,
        method=method,
        path=path,
    )
    return receipt_id, request_binding, resolver_id, proposal_id


def identity_mutation_reconciliation_resolver_id(
    mutation: dict[str, Any],
) -> str | None:
    request_binding = mutation.get("request")
    if not isinstance(request_binding, dict):
        return None
    method = request_binding.get("method")
    path = request_binding.get("path")
    if not isinstance(method, str) or not isinstance(path, str):
        return None
    try:
        resolver_id, _proposal_id = mutation_route_resolution(
            mutation,
            method=method,
            path=path,
        )
    except IdentityMutationError:
        return None
    return resolver_id


def _require_resolver_contract(
    mutation: dict[str, Any],
    *,
    resolver_id: str,
    request_binding: dict[str, Any],
) -> IdentityMutationResolverContract:
    _by_route, by_resolver = _contract_maps()
    contract = by_resolver.get(resolver_id)
    if contract is None:
        raise IdentityMutationError("no typed reconciliation resolver for this capability")
    method = request_binding.get("method")
    path = request_binding.get("path")
    if method != contract.method or not isinstance(path, str):
        raise IdentityMutationError("mutation route differs from executable resolver contract")
    route_regex, _path_format, _convertors = compile_path(contract.canonical_path_template)
    if route_regex.fullmatch(path) is None:
        raise IdentityMutationError("mutation route differs from executable resolver contract")
    if mutation.get("schema") == "finharness.api_mutation_identity_receipt.v2":
        binding = mutation.get("route_capability")
        if not isinstance(binding, dict):
            raise IdentityMutationError("mutation route capability binding is missing")
        if (
            binding.get("capability_id") != contract.capability_id
            or binding.get("resolver_id") != contract.resolver_id
            or binding.get("method") != contract.method
            or binding.get("canonical_path_template") != contract.canonical_path_template
        ):
            raise IdentityMutationError(
                "mutation route/resolver mapping differs from executable contract"
            )
    return contract


def reconcile_identity_mutation_from_domain_truth(
    receipt_path: str | Path,
    *,
    engine: Engine,
    receipt_root: str | Path,
    reconciled_by: str,
    reason: str,
    resolver_services: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    """Dispatch one pending mutation through its declared typed resolver contract."""

    mutation_path = Path(receipt_path)
    mutation = load_identity_mutation_receipt(mutation_path)
    receipt_id, request_binding, resolver_id, proposal_id = require_pending_identity_mutation_route(
        mutation
    )
    contract = _require_resolver_contract(
        mutation,
        resolver_id=resolver_id,
        request_binding=request_binding,
    )
    handler_kwargs: dict[str, Any] = {
        "mutation": mutation,
        "receipt_id": receipt_id,
        "request_binding": request_binding,
        "proposal_id": proposal_id,
        "engine": engine,
        "receipt_root": Path(receipt_root),
        "reconciled_by": reconciled_by,
        "reason": reason,
    }
    if contract.service_key is not None:
        handler_kwargs[contract.service_key] = (resolver_services or {}).get(contract.service_key)
    return contract.handler(mutation_path, **handler_kwargs)
