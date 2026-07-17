"""Governed proposal and human-attestation API routes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Engine, desc
from sqlmodel import Session, select
from starlette.routing import compile_path

from finharness.api.dependencies import (
    EngineDependency,
    ReceiptRootDependency,
    WriteCapabilityDependency,
)
from finharness.api.keyed_mutation_capabilities import (
    IdentityMutationResolverContract,
    KeyedMutationCapabilityError,
    KeyedMutationRouteMode,
    identity_mutation_resolver_contract_maps,
    load_keyed_mutation_route_capabilities,
)
from finharness.identity import (
    IdentityMutationClaim,
    IdentityMutationError,
    OperatorContext,
    authoritative_actor_id_from_binding,
    bind_authenticated_actor_to_mutation,
    load_identity_mutation_receipt,
    load_identity_mutation_receipt_by_id,
    record_verified_identity_mutation_reconciliation,
    replay_identity_mutation,
)
from finharness.identity import (
    identity_mutation_source_ref as canonical_identity_mutation_source_ref,
)
from finharness.project_paths import ROOT
from finharness.proposal_queue_checks import (
    ProposalQueueChecks,
    build_proposal_queue_checks,
)
from finharness.review_read import read_proposal_timeline
from finharness.scaffold_candidate_preflight import (
    SCAFFOLD_CANDIDATE_PREFLIGHT_NON_CLAIMS,
    PreflightFinding,
    ScaffoldCandidatePreflightReport,
    find_scaffold_revision_candidate,
    preflight_scaffold_revision_candidate,
)
from finharness.statecore.decision_scaffold import DecisionScaffoldError
from finharness.statecore.models import (
    Attestation,
    Proposal,
    ReceiptIndex,
    ReviewEvent,
)
from finharness.statecore.proposal_revisions import walk_proposal_revisions
from finharness.statecore.proposal_version import (
    CurrentProposalVersion,
    ProposalVersionResolutionError,
    resolve_current_proposal_version,
)
from finharness.statecore.proposals import (
    ReviewEventKind,
    archived_proposal_ids,
    create_governed_attestation,
    create_governed_proposal,
    create_governed_review_event,
    proposal_content_hash,
    revise_governed_proposal_scaffold,
)
from finharness.statecore.risk_classification import HighRiskConfirmationError
from finharness.statecore.store import StateCoreStoreError

router = APIRouter(tags=["proposals"])

DecisionInput = Literal["approved", "rejected", "deferred"]


class ProposalCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    claim: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    limitations: dict[str, Any] = Field(default_factory=dict)
    non_claims: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    decision_scaffold: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind", "claim")
    @classmethod
    def require_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("proposal kind and claim are required")
        return value


class ProposalCreateResponse(BaseModel):
    proposal: Proposal
    receipt_ref: str
    execution_allowed: bool = False


_PROPOSAL_CREATE_RECONCILIATION_RESOLVER = "finharness.api.proposal_create.v1"
def proposal_id_for_identity_mutation(receipt_id: str) -> str:
    """Derive one stable Proposal id from one mutation receipt."""

    digest = hashlib.sha256(receipt_id.encode()).hexdigest()[:24]
    return f"prop_api_{digest}"


def identity_mutation_source_ref(receipt_id: str) -> str:
    return canonical_identity_mutation_source_ref(receipt_id)


def _route_identity_mutation_binding(
    http_request: Request,
    *,
    effect_kind: str,
    operator: OperatorContext | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Bind one route-owned effect to its executing identity claim."""

    raw_claim = getattr(
        http_request.state,
        "identity_mutation_claim",
        None,
    )

    if raw_claim is None:
        return None

    if not isinstance(raw_claim, IdentityMutationClaim) or raw_claim.disposition != "execute":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invalid_idempotency_contract",
                "message": ("The executing mutation claim is invalid."),
                "execution_allowed": False,
            },
        )

    request_binding = raw_claim.payload.get(
        "request",
    )
    route_capability = raw_claim.payload.get("route_capability")
    mutation_schema = raw_claim.payload.get("schema")

    if not isinstance(request_binding, dict) or (
        mutation_schema == "finharness.api_mutation_identity_receipt.v2"
        and not isinstance(route_capability, dict)
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invalid_idempotency_contract",
                "message": ("The mutation request binding is invalid."),
                "execution_allowed": False,
            },
        )

    method = request_binding.get("method")
    path = request_binding.get("path")
    target = request_binding.get("target")
    body_sha256 = request_binding.get(
        "body_sha256",
    )

    if (
        not isinstance(method, str)
        or not isinstance(path, str)
        or not isinstance(target, str)
        or not isinstance(body_sha256, str)
        or method != http_request.method
        or path != http_request.url.path
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "invalid_idempotency_contract",
                "message": ("The mutation request binding does not match the executing route."),
                "execution_allowed": False,
            },
        )

    actor_binding: tuple[str, dict[str, object]] | None = None
    if operator is not None:
        try:
            actor_binding = bind_authenticated_actor_to_mutation(
                raw_claim,
                context=operator,
            )
        except IdentityMutationError as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "invalid_authenticated_actor_binding",
                    "message": str(exc),
                    "execution_allowed": False,
                },
            ) from exc

    source_ref = identity_mutation_source_ref(raw_claim.receipt_id)
    actor_context: dict[str, Any] = {}
    if actor_binding is not None:
        actor_ref, actor = actor_binding
        actor_context = {
            "authenticated_actor_receipt_ref": actor_ref,
            "authenticated_actor": actor,
        }

    capability_context: dict[str, Any] = {}
    domain_binding_schema = "finharness.api_domain_mutation_binding.v1"
    if isinstance(route_capability, dict):
        domain_binding_schema = "finharness.api_domain_mutation_binding.v2"
        capability_context = {
            "identity_mutation_route_capability_id": (
                route_capability.get("capability_id")
            ),
            "identity_mutation_route_capability_sha256": (
                route_capability.get("capability_sha256")
            ),
            "identity_mutation_canonical_path_template": (
                route_capability.get("canonical_path_template")
            ),
            "identity_mutation_resolver_id": route_capability.get("resolver_id"),
        }

    return (
        source_ref,
        {
            "schema": domain_binding_schema,
            "effect_kind": effect_kind,
            "identity_mutation_receipt_id": (raw_claim.receipt_id),
            "identity_mutation_request_body_sha256": (body_sha256),
            "identity_mutation_request_target": target,
            "identity_mutation_method": method,
            "identity_mutation_path": path,
            **capability_context,
            **actor_context,
            "execution_allowed": False,
        },
    )


def proposal_create_response_payload(
    proposal: Proposal,
    *,
    receipt_ref: str,
) -> dict[str, Any]:
    """Build the single canonical Proposal-create response contract."""

    return ProposalCreateResponse(
        proposal=proposal,
        receipt_ref=receipt_ref,
        execution_allowed=False,
    ).model_dump(mode="json")


def _require_proposal_create_mutation_binding(
    mutation: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    request_binding = mutation.get("request")
    if not isinstance(request_binding, dict):
        raise IdentityMutationError("mutation receipt request binding is missing")
    if request_binding.get("method") != "POST" or request_binding.get("path") != "/proposals":
        raise IdentityMutationError("no typed reconciliation resolver for this mutation route")

    receipt_id = mutation.get("receipt_id")
    if not isinstance(receipt_id, str) or not receipt_id:
        raise IdentityMutationError("mutation receipt id is missing")
    return receipt_id, request_binding


def _load_verified_proposal_effect(
    *,
    receipt_id: str,
    engine: Engine,
    receipt_root: Path,
) -> tuple[Proposal, str, str, dict[str, Any]]:
    proposal_id = proposal_id_for_identity_mutation(receipt_id)
    mutation_ref = identity_mutation_source_ref(receipt_id)

    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)

    if proposal is None:
        raise IdentityMutationError("verified proposal effect not found; mutation remains pending")
    if mutation_ref not in proposal.source_refs:
        raise IdentityMutationError("proposal effect is not bound to the mutation receipt")

    domain_receipt_ref = proposal.receipt_ref
    if not domain_receipt_ref:
        raise IdentityMutationError("proposal effect has no canonical domain receipt")

    snapshot_proposal, domain_receipt = _verified_proposal_snapshot(
        domain_receipt_ref,
        receipt_root=receipt_root,
    )

    if snapshot_proposal.model_dump(mode="json") != proposal.model_dump(mode="json"):
        raise IdentityMutationError("proposal row and domain receipt snapshot do not match")

    return (
        proposal,
        mutation_ref,
        domain_receipt_ref,
        domain_receipt,
    )


def _require_proposal_domain_receipt_binding(
    *,
    proposal: Proposal,
    domain_receipt: dict[str, Any],
    receipt_id: str,
    request_binding: dict[str, Any],
    route_capability: object,
) -> None:
    if domain_receipt.get("kind") != "state_core_proposal":
        raise IdentityMutationError("domain receipt is not a proposal receipt")
    if domain_receipt.get("proposal") != proposal.model_dump(mode="json"):
        raise IdentityMutationError("proposal row and domain receipt do not match")
    if domain_receipt.get("content_hash") != proposal_content_hash(proposal):
        raise IdentityMutationError("proposal domain receipt content hash does not match")

    revision_context = domain_receipt.get("revision_context")
    if not isinstance(revision_context, dict):
        raise IdentityMutationError("proposal domain receipt has no mutation binding")

    if revision_context.get("kind") != "api_proposal_create":
        raise IdentityMutationError("proposal domain receipt is not a proposal create receipt")

    _require_exact_domain_binding(
        revision_context,
        receipt_id=receipt_id,
        request_binding=request_binding,
        route_capability=route_capability,
        effect_kind="api_proposal_create",
    )


def reconcile_proposal_create_identity_mutation(
    receipt_path: str | Path,
    *,
    engine: Engine,
    receipt_root: str | Path,
    reconciled_by: str,
    reason: str,
) -> dict[str, Any]:
    """Reconcile POST /proposals from verified StateCore truth only."""

    mutation_path = Path(receipt_path)
    mutation = load_identity_mutation_receipt(mutation_path)
    if mutation.get("state") != "pending":
        raise IdentityMutationError("only a pending mutation can be reconciled")

    receipt_id, request_binding, resolver_id, proposal_id = (
        _require_pending_mutation_route(mutation)
    )
    if (
        resolver_id != _PROPOSAL_CREATE_RECONCILIATION_RESOLVER
        or proposal_id is not None
    ):
        raise IdentityMutationError("mutation capability is not Proposal create")
    (
        proposal,
        mutation_ref,
        domain_receipt_ref,
        domain_receipt,
    ) = _load_verified_proposal_effect(
        receipt_id=receipt_id,
        engine=engine,
        receipt_root=Path(receipt_root),
    )
    _require_proposal_domain_receipt_binding(
        proposal=proposal,
        domain_receipt=domain_receipt,
        receipt_id=receipt_id,
        request_binding=request_binding,
        route_capability=mutation.get("route_capability"),
    )

    response_payload = proposal_create_response_payload(
        proposal,
        receipt_ref=domain_receipt_ref,
    )
    response_body = json.dumps(
        response_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()

    return record_verified_identity_mutation_reconciliation(
        mutation_path,
        expected_payload=mutation,
        reconciled_by=reconciled_by,
        reason=reason,
        resolver_id=_PROPOSAL_CREATE_RECONCILIATION_RESOLVER,
        evidence_refs=[
            mutation_ref,
            domain_receipt_ref,
        ],
        domain_effect={
            "kind": "proposal_create",
            "proposal_id": proposal.proposal_id,
            "proposal_content_hash": proposal_content_hash(proposal),
            "receipt_ref": domain_receipt_ref,
            "canonical_resource": (f"/proposals/{proposal.proposal_id}"),
            "execution_allowed": False,
        },
        status_code=200,
        response_body=response_body,
        content_type="application/json",
    )


_ATTESTATION_CREATE_RECONCILIATION_RESOLVER = "finharness.api.attestation_create.v1"
_SCAFFOLD_REVISION_RECONCILIATION_RESOLVER = "finharness.api.proposal_scaffold_revision.v1"
_REVIEW_EVENT_CREATE_RECONCILIATION_RESOLVER = "finharness.api.review_event_create.v1"


def _legacy_v1_proposal_mutation_route(
    *,
    method: str,
    path: str,
) -> tuple[str | None, str | None]:
    if method == "POST" and path == "/proposals":
        return (
            _PROPOSAL_CREATE_RECONCILIATION_RESOLVER,
            None,
        )

    parts = path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "proposals" or not parts[1]:
        return None, None

    proposal_id = parts[1]
    operation = parts[2]

    if method == "POST" and operation == "attest":
        return (
            _ATTESTATION_CREATE_RECONCILIATION_RESOLVER,
            proposal_id,
        )

    if method == "PATCH" and operation == "decision-scaffold":
        return (
            _SCAFFOLD_REVISION_RECONCILIATION_RESOLVER,
            proposal_id,
        )

    if method == "POST" and operation == "review-events":
        return (
            _REVIEW_EVENT_CREATE_RECONCILIATION_RESOLVER,
            proposal_id,
        )

    return None, None


def identity_mutation_reconciliation_resolver_id(
    mutation: dict[str, Any],
) -> str | None:
    request_binding = mutation.get("request")
    if not isinstance(request_binding, dict):
        return None

    method = request_binding.get("method")
    path = request_binding.get("path")

    if not isinstance(method, str):
        return None
    if not isinstance(path, str):
        return None

    try:
        resolver_id, _proposal_id = _mutation_route_resolution(
            mutation,
            method=method,
            path=path,
        )
    except IdentityMutationError:
        return None
    return resolver_id


def _v2_mutation_route_resolution(
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
    registry = load_keyed_mutation_route_capabilities()
    capability = registry.by_id(capability_id)
    if capability is None or binding != capability.receipt_binding():
        raise IdentityMutationError(
            "mutation route capability does not match the canonical registry"
        )
    if (
        capability.mode
        is not KeyedMutationRouteMode.TYPED_DOMAIN_RECONCILIATION
        or capability.resolver_id is None
    ):
        raise IdentityMutationError(
            "mutation route capability has no typed reconciliation resolver"
        )
    if method != capability.method:
        raise IdentityMutationError("mutation method differs from route capability")
    route_regex, _path_format, _convertors = compile_path(
        capability.canonical_path_template
    )
    matched = route_regex.fullmatch(path)
    if matched is None:
        raise IdentityMutationError("mutation path differs from route capability")
    return capability.resolver_id, matched.groupdict().get("proposal_id")


def _mutation_route_resolution(
    mutation: dict[str, Any],
    *,
    method: str,
    path: str,
) -> tuple[str, str | None]:
    schema = mutation.get("schema")
    if schema == "finharness.api_mutation_identity_receipt.v2":
        return _v2_mutation_route_resolution(
            mutation,
            method=method,
            path=path,
        )
    if schema != "finharness.api_mutation_identity_receipt.v1":
        raise IdentityMutationError("unsupported mutation receipt schema")
    resolver_id, proposal_id = _legacy_v1_proposal_mutation_route(
        method=method,
        path=path,
    )
    if resolver_id is None:
        raise IdentityMutationError(
            "no typed reconciliation resolver for this mutation route"
        )
    return resolver_id, proposal_id


def _require_pending_mutation_route(
    mutation: dict[str, Any],
) -> tuple[
    str,
    dict[str, Any],
    str,
    str | None,
]:
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

    resolver_id, proposal_id = _mutation_route_resolution(
        mutation,
        method=method,
        path=path,
    )

    return (
        receipt_id,
        request_binding,
        resolver_id,
        proposal_id,
    )


def _resolve_typed_domain_receipt(
    receipt_ref: str,
    *,
    receipt_root: Path,
    expected_directory: str,
) -> Path:
    candidate = Path(receipt_ref)
    if not candidate.is_absolute():
        candidate = ROOT / candidate

    if candidate.is_symlink():
        raise IdentityMutationError("domain receipt cannot be a symlink")

    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise IdentityMutationError("domain receipt is missing or unreadable") from exc

    allowed_root = (receipt_root / expected_directory).resolve()

    if not resolved.is_relative_to(allowed_root):
        raise IdentityMutationError("domain receipt is outside its typed receipt directory")

    if not resolved.is_file():
        raise IdentityMutationError("domain receipt is not a regular file")

    return resolved


def _load_typed_domain_receipt(
    receipt_ref: str,
    *,
    receipt_root: Path,
    expected_directory: str,
) -> tuple[Path, dict[str, Any]]:
    path = _resolve_typed_domain_receipt(
        receipt_ref,
        receipt_root=receipt_root,
        expected_directory=expected_directory,
    )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise IdentityMutationError("domain receipt is unreadable") from exc

    if not isinstance(payload, dict):
        raise IdentityMutationError("domain receipt is not a JSON object")

    return path, payload


def _domain_receipt_sha256(
    payload: dict[str, Any],
) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def _canonical_response_body(
    response: BaseModel,
) -> bytes:
    return json.dumps(
        response.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()


def _require_exact_domain_binding(
    context: Any,
    *,
    receipt_id: str,
    request_binding: dict[str, Any],
    route_capability: object,
    effect_kind: str,
    expected_actor: object | None = None,
) -> None:
    if not isinstance(context, dict):
        raise IdentityMutationError("domain receipt has no typed mutation binding")

    expected = {
        "effect_kind": effect_kind,
        "identity_mutation_receipt_id": receipt_id,
        "identity_mutation_request_body_sha256": (request_binding.get("body_sha256")),
        "identity_mutation_request_target": (request_binding.get("target")),
        "identity_mutation_method": (request_binding.get("method")),
        "identity_mutation_path": (request_binding.get("path")),
        "execution_allowed": False,
    }
    if route_capability is None:
        expected["schema"] = "finharness.api_domain_mutation_binding.v1"
    elif isinstance(route_capability, dict):
        expected |= {
            "schema": "finharness.api_domain_mutation_binding.v2",
            "identity_mutation_route_capability_id": (
                route_capability.get("capability_id")
            ),
            "identity_mutation_route_capability_sha256": (
                route_capability.get("capability_sha256")
            ),
            "identity_mutation_canonical_path_template": (
                route_capability.get("canonical_path_template")
            ),
            "identity_mutation_resolver_id": route_capability.get("resolver_id"),
        }
    else:
        raise IdentityMutationError("identity mutation route capability is invalid")

    for key, value in expected.items():
        if context.get(key) != value:
            raise IdentityMutationError(f"domain receipt mutation binding does not match: {key}")
    if expected_actor is not None:
        if context.get("authenticated_actor") != expected_actor:
            raise IdentityMutationError("domain receipt authenticated actor does not match")
        if context.get("authenticated_actor_receipt_ref") != identity_mutation_source_ref(
            receipt_id
        ):
            raise IdentityMutationError("domain receipt authenticated actor ref does not match")


def _require_unqueried_route_target(
    request_binding: dict[str, Any],
) -> None:
    path = request_binding.get("path")
    target = request_binding.get("target")

    if target != path:
        raise IdentityMutationError(
            "typed Cockpit reconciliation does not accept query-bearing mutation targets"
        )


def _single_bound_effect(
    values: list[Any],
    *,
    mutation_ref: str,
    label: str,
) -> Any:
    matches = [
        value for value in values if mutation_ref in list(getattr(value, "source_refs", []) or [])
    ]

    if not matches:
        raise IdentityMutationError(f"verified {label} effect not found; mutation remains pending")

    if len(matches) != 1:
        raise IdentityMutationError(f"multiple {label} effects are bound to one mutation receipt")

    return matches[0]


def _receipt_ref_from_source_refs(
    source_refs: list[str],
    *,
    directory: str,
) -> str:
    matches = [ref for ref in source_refs if isinstance(ref, str) and directory in Path(ref).parts]

    if len(matches) != 1:
        raise IdentityMutationError(f"domain row does not identify exactly one {directory} receipt")

    return matches[0]


def _verified_proposal_snapshot(
    receipt_ref: str,
    *,
    receipt_root: Path,
) -> tuple[Proposal, dict[str, Any]]:
    _path, receipt = _load_typed_domain_receipt(
        receipt_ref,
        receipt_root=receipt_root,
        expected_directory="proposals",
    )

    if receipt.get("kind") != "state_core_proposal":
        raise IdentityMutationError("referenced proposal receipt has the wrong kind")

    proposal_payload = receipt.get("proposal")
    if not isinstance(proposal_payload, dict):
        raise IdentityMutationError("proposal receipt snapshot is missing")

    try:
        proposal = Proposal.model_validate(proposal_payload)
    except ValueError as exc:
        raise IdentityMutationError("proposal receipt snapshot is invalid") from exc

    if proposal.receipt_ref != receipt_ref:
        raise IdentityMutationError("proposal snapshot receipt ref does not match its receipt")

    if receipt.get("content_hash") != proposal_content_hash(proposal):
        raise IdentityMutationError("proposal receipt content hash does not match its snapshot")

    return proposal, receipt


def _record_typed_reconciliation(
    mutation_path: Path,
    *,
    mutation: dict[str, Any],
    resolver_id: str,
    reconciled_by: str,
    reason: str,
    evidence_refs: list[str],
    domain_effect: dict[str, Any],
    response: BaseModel,
) -> dict[str, Any]:
    return record_verified_identity_mutation_reconciliation(
        mutation_path,
        expected_payload=mutation,
        reconciled_by=reconciled_by,
        reason=reason,
        resolver_id=resolver_id,
        evidence_refs=evidence_refs,
        domain_effect=domain_effect,
        status_code=200,
        response_body=_canonical_response_body(response),
        content_type="application/json",
    )


def _reconcile_attestation_identity_mutation(
    mutation_path: Path,
    *,
    mutation: dict[str, Any],
    receipt_id: str,
    request_binding: dict[str, Any],
    proposal_id: str,
    engine: Engine,
    receipt_root: Path,
    reconciled_by: str,
    reason: str,
) -> dict[str, Any]:
    _require_unqueried_route_target(request_binding)
    mutation_ref = identity_mutation_source_ref(receipt_id)

    with Session(engine) as session:
        current_proposal = session.get(
            Proposal,
            proposal_id,
        )
        attestations = list(
            session.exec(select(Attestation).where(Attestation.proposal_id == proposal_id)).all()
        )

    if current_proposal is None:
        raise IdentityMutationError("attestation proposal no longer exists")

    attestation = _single_bound_effect(
        attestations,
        mutation_ref=mutation_ref,
        label="attestation",
    )

    receipt_ref = _receipt_ref_from_source_refs(
        attestation.source_refs,
        directory="attestations",
    )
    _path, receipt = _load_typed_domain_receipt(
        receipt_ref,
        receipt_root=receipt_root,
        expected_directory="attestations",
    )

    if receipt.get("kind") != ("state_core_attestation"):
        raise IdentityMutationError("domain receipt is not an attestation receipt")

    if receipt.get("attestation") != attestation.model_dump(mode="json"):
        raise IdentityMutationError("attestation row and receipt do not match")

    if receipt.get("proposal_id") != proposal_id:
        raise IdentityMutationError("attestation receipt proposal id does not match the route")

    _require_exact_domain_binding(
        receipt.get("mutation_context"),
        receipt_id=receipt_id,
        request_binding=request_binding,
        route_capability=mutation.get("route_capability"),
        effect_kind="api_attestation_create",
        expected_actor=mutation.get("actor"),
    )
    expected_actor_id = authoritative_actor_id_from_binding(mutation.get("actor"))
    if attestation.attester != expected_actor_id:
        raise IdentityMutationError("attestation row actor differs from authenticated actor")

    proposal_receipt_ref = receipt.get("proposal_receipt_ref")
    if not isinstance(
        proposal_receipt_ref,
        str,
    ):
        raise IdentityMutationError("attestation receipt has no bound proposal receipt")

    proposal, _proposal_receipt = _verified_proposal_snapshot(
        proposal_receipt_ref,
        receipt_root=receipt_root,
    )

    if proposal.proposal_id != proposal_id:
        raise IdentityMutationError("attestation proposal snapshot does not match the route")

    response = AttestationCreateResponse(
        attestation=attestation,
        proposal=proposal,
        receipt_ref=receipt_ref,
        approved_is_not_execution_authorization=True,
        execution_allowed=False,
    )

    return _record_typed_reconciliation(
        mutation_path,
        mutation=mutation,
        resolver_id=(_ATTESTATION_CREATE_RECONCILIATION_RESOLVER),
        reconciled_by=reconciled_by,
        reason=reason,
        evidence_refs=[
            mutation_ref,
            receipt_ref,
            proposal_receipt_ref,
        ],
        domain_effect={
            "kind": "attestation_create",
            "attestation_id": (attestation.attestation_id),
            "proposal_id": proposal_id,
            "receipt_ref": receipt_ref,
            "receipt_sha256": (_domain_receipt_sha256(receipt)),
            "canonical_resource": (f"/proposals/{proposal_id}"),
            "execution_allowed": False,
        },
        response=response,
    )


_MUTATION_BINDING_FIELDS = frozenset(
    {
        "identity_mutation_receipt_id",
        "identity_mutation_request_body_sha256",
        "identity_mutation_request_target",
        "identity_mutation_method",
        "identity_mutation_path",
        "identity_mutation_route_capability_id",
        "identity_mutation_route_capability_sha256",
        "identity_mutation_canonical_path_template",
        "identity_mutation_resolver_id",
        "schema",
        "effect_kind",
        "authenticated_actor",
        "authenticated_actor_receipt_ref",
    }
)


def _require_no_partial_mutation_binding(
    context: dict[str, Any],
) -> None:
    """Reject a scaffold revision_context that carries mutation-binding
    fields without an identity_mutation_receipt_id.

    A legitimate unkeyed revision has none of these fields.  Partial
    bindings are corrupt evidence and must fail closed.
    """
    partial = sorted(_MUTATION_BINDING_FIELDS & set(context))
    if partial:
        raise IdentityMutationError(
            "scaffold revision context has partial mutation-binding "
            "fields without identity_mutation_receipt_id: " + ", ".join(partial)
        )


def _require_verifiable_foreign_mutation_claim(
    *,
    claim_id: object,
    context: dict[str, Any],
    candidate_proposal: Proposal,
    candidate_ref: str,
    receipt_root: Path,
    previous_receipt_ref: str | None,
    changed_fields: list[str],
) -> None:
    """Verify that a foreign mutation claim is a proven, terminal domain effect.

    A scaffold candidate that claims a different identity_mutation_receipt_id
    is only a legitimate inherited reference if **all** of the following hold:

    1. The foreign identity receipt exists, has valid integrity, and its
       internal ``receipt_id`` matches the canonical ID.
    2. The foreign receipt is in a terminal state (committed or
       reconciled_applied).
    3. The foreign request is a PATCH to the **same proposal's**
       decision-scaffold route without query.
    4. The foreign receipt's canonical terminal response can be decoded,
       hash-validated, and parsed through the real scaffold revision
       response model.
    5. The terminal response points to **this** candidate receipt, its
       proposal snapshot matches the candidate's proposal snapshot, and
       the response fields match the candidate's revision_context.

    If any step cannot be proven, the candidate is not a verified foreign
    effect and reconciliation must fail closed.
    """
    # ── 1.  Claim ID validity ──────────────────────────────────────
    if not isinstance(claim_id, str) or not claim_id:
        raise IdentityMutationError("scaffold candidate foreign claim id is not a valid receipt id")

    expected_ref = identity_mutation_source_ref(claim_id)
    if expected_ref not in candidate_proposal.source_refs:
        raise IdentityMutationError(
            "scaffold candidate claims foreign receipt_id "
            "but snapshot does not contain its mutation ref"
        )

    # ── 2.  Load foreign identity receipt via typed loader ─────────
    try:
        foreign_receipt = load_identity_mutation_receipt_by_id(
            receipt_root / "identity",
            claim_id,
        )
    except IdentityMutationError:
        raise
    except (OSError, ValueError) as exc:
        raise IdentityMutationError(
            "scaffold candidate claims foreign receipt_id "
            "but the identity receipt is missing or invalid"
        ) from exc

    # ── 3.  Terminal state ────────────────────────────────────────
    foreign_state = foreign_receipt.get("state")
    if foreign_state not in ("committed", "reconciled_applied"):
        raise IdentityMutationError(
            f"scaffold candidate foreign receipt state is {foreign_state!r}, "
            "not a proven terminal domain effect"
        )

    # ── 4.  Route ownership ───────────────────────────────────────
    foreign_request = foreign_receipt.get("request")
    if not isinstance(foreign_request, dict):
        raise IdentityMutationError(
            "scaffold candidate foreign identity receipt has no request binding"
        )

    target_proposal_id = candidate_proposal.proposal_id
    expected_path = f"/proposals/{target_proposal_id}/decision-scaffold"

    if foreign_request.get("method") != "PATCH":
        raise IdentityMutationError("scaffold candidate foreign request is not a PATCH")
    if foreign_request.get("path") != expected_path:
        raise IdentityMutationError(
            "scaffold candidate foreign request is not for the same proposal's scaffold route"
        )
    if foreign_request.get("target") != expected_path:
        raise IdentityMutationError(
            "scaffold candidate foreign request target does not match the scaffold route"
        )

    # ── 5.  Exact binding between context and foreign request ─────
    _require_exact_domain_binding(
        context,
        receipt_id=claim_id,
        request_binding=foreign_request,
        route_capability=foreign_receipt.get("route_capability"),
        effect_kind="api_proposal_decision_scaffold_revision",
        expected_actor=foreign_receipt.get("actor"),
    )
    if context.get("attester") != authoritative_actor_id_from_binding(
        foreign_receipt.get("actor")
    ):
        raise IdentityMutationError(
            "scaffold candidate foreign actor differs from authenticated actor"
        )

    # ── 6.  Canonical terminal response → candidate ownership ─────
    _require_foreign_response_ownership(
        foreign_receipt,
        candidate_proposal=candidate_proposal,
        candidate_ref=candidate_ref,
        previous_receipt_ref=previous_receipt_ref,
        changed_fields=changed_fields,
    )


def _require_foreign_response_ownership(
    foreign_receipt: dict[str, Any],
    *,
    candidate_proposal: Proposal,
    candidate_ref: str,
    previous_receipt_ref: str | None,
    changed_fields: list[str],
) -> None:
    """Verify the foreign terminal response points to this candidate receipt.

    The previous_receipt_ref and changed_fields must already have been
    validated by the common scaffold candidate integrity helper — this
    function only proves the foreign terminal response agrees with them.
    """
    try:
        status_code, body, content_type = replay_identity_mutation(foreign_receipt)
    except IdentityMutationError as err:
        raise IdentityMutationError(
            "scaffold candidate foreign receipt has no valid terminal response"
        ) from err

    if status_code != 200:
        raise IdentityMutationError(
            "scaffold candidate foreign terminal response status is not 200"
        )
    if content_type != "application/json":
        raise IdentityMutationError("scaffold candidate foreign terminal response is not JSON")

    try:
        foreign_response = ProposalScaffoldRevisionResponse.model_validate_json(body)
    except Exception as err:
        raise IdentityMutationError(
            "scaffold candidate foreign terminal response is not a valid scaffold revision"
        ) from err

    if foreign_response.receipt_ref != candidate_ref:
        raise IdentityMutationError(
            "scaffold candidate foreign terminal response does not point to this candidate receipt"
        )

    if foreign_response.proposal.receipt_ref != candidate_ref:
        raise IdentityMutationError(
            "scaffold candidate foreign terminal response proposal receipt_ref does not match"
        )

    if foreign_response.proposal.model_dump(mode="json") != candidate_proposal.model_dump(
        mode="json"
    ):
        raise IdentityMutationError(
            "scaffold candidate foreign terminal response proposal"
            " does not match candidate snapshot"
        )

    if foreign_response.execution_allowed is not False:
        raise IdentityMutationError(
            "scaffold candidate foreign terminal response execution_allowed is not False"
        )

    if foreign_response.previous_receipt_ref != previous_receipt_ref:
        raise IdentityMutationError(
            "scaffold candidate foreign terminal response"
            " previous_receipt_ref does not match context"
        )

    if tuple(changed_fields) != foreign_response.changed_scaffold_fields:
        raise IdentityMutationError(
            "scaffold candidate foreign terminal response changed_scaffold_fields "
            "does not match context"
        )


def _require_common_scaffold_candidate_integrity(
    *,
    candidate_proposal: Proposal,
    candidate_receipt: dict[str, Any],
    context: dict[str, Any],
    proposal_id: str,
) -> tuple[str | None, list[str]]:
    """Validate scaffold candidate integrity before claim classification.

    Every scaffold candidate — whether unkeyed inherited, foreign keyed,
    or exact keyed — must pass these checks.  No candidate may skip
    common verification and jump directly to claim disposition.
    """

    # 4.1  Proposal ownership
    if candidate_proposal.proposal_id != proposal_id:
        raise IdentityMutationError(
            "scaffold candidate proposal id does not match the reconciliation route"
        )

    # 4.2  previous_receipt_ref
    previous_receipt_ref = context.get("previous_receipt_ref")

    if previous_receipt_ref is not None and not isinstance(previous_receipt_ref, str):
        raise IdentityMutationError("scaffold previous receipt ref is invalid")

    if isinstance(previous_receipt_ref, str) and not previous_receipt_ref:
        raise IdentityMutationError("scaffold previous receipt ref is an empty string")

    # 4.3  changed_scaffold_fields
    changed_fields = context.get("changed_scaffold_fields")

    if (
        not isinstance(changed_fields, list)
        or not changed_fields
        or not all(isinstance(field, str) and field for field in changed_fields)
        or len(changed_fields) != len(set(changed_fields))
    ):
        raise IdentityMutationError("scaffold changed-field evidence is invalid")

    # 4.4  supersedes
    if candidate_receipt.get("supersedes") != previous_receipt_ref:
        raise IdentityMutationError("scaffold supersedes link does not match revision context")

    return previous_receipt_ref, changed_fields


def _validate_scaffold_candidate_revision(
    candidate_ref: str,
    *,
    receipt_id: str,
    request_binding: dict[str, Any],
    proposal_id: str,
    receipt_root: Path,
    mutation_ref: str,
    expected_actor: object,
    route_capability: object,
) -> tuple[str, Proposal, dict[str, Any]] | None:
    """Validate one candidate scaffold revision receipt against an exact identity mutation.

    Returns (receipt_ref, proposal, receipt) when the candidate is an exact match.
    Returns None when the candidate is a verified inherited candidate
    (belongs to a different revision and is fully readable).
    Raises IdentityMutationError on any unverifiable, corrupt, or
    inconsistent evidence — a candidate that cannot be fully validated
    must block reconciliation, not be silently skipped.
    """
    # 1. Load typed proposal receipt.  Any failure here is a corrupt
    #    candidate and must fail closed — the system cannot distinguish
    #    "inherited ref on a broken receipt" from "second domain effect
    #    whose evidence was damaged".
    candidate_proposal, candidate_receipt = _verified_proposal_snapshot(
        candidate_ref,
        receipt_root=receipt_root,
    )

    # 2. Index must agree with the immutable domain snapshot.
    if mutation_ref not in candidate_proposal.source_refs:
        raise IdentityMutationError(
            "scaffold candidate index claims mutation ref but proposal snapshot does not contain it"
        )

    # 3. Must have a revision_context of the correct kind.
    context = candidate_receipt.get("revision_context")
    if not isinstance(context, dict):
        raise IdentityMutationError("scaffold candidate receipt has no revision context")

    if context.get("kind") != "decision_scaffold_revision":
        raise IdentityMutationError("scaffold candidate is not a decision scaffold revision")

    # 4. Common scaffold candidate integrity — runs BEFORE classification.
    #    Every candidate, including foreign, must pass these checks.
    previous_receipt_ref, changed_fields = _require_common_scaffold_candidate_integrity(
        candidate_proposal=candidate_proposal,
        candidate_receipt=candidate_receipt,
        context=context,
        proposal_id=proposal_id,
    )

    # 5. Claim disposition classification.
    claim_id = context.get("identity_mutation_receipt_id")

    if not claim_id:
        # Unkeyed later revision — must carry zero mutation-binding
        # fields; partial bindings are corrupt evidence.
        _require_no_partial_mutation_binding(context)
        return None

    if claim_id != receipt_id:
        # Candidate claims to belong to a different mutation.
        # This is only safe to skip if the foreign claim can be
        # independently verified as a real, intact identity receipt.
        _require_verifiable_foreign_mutation_claim(
            claim_id=claim_id,
            context=context,
            candidate_proposal=candidate_proposal,
            candidate_ref=candidate_ref,
            receipt_root=receipt_root,
            previous_receipt_ref=previous_receipt_ref,
            changed_fields=changed_fields,
        )
        return None

    # 6. Candidate **claims** this exact receipt_id.
    #    Full binding validation is mandatory; any mismatch
    #    is evidence of a tampered or inconsistent receipt.
    _require_exact_domain_binding(
        context,
        receipt_id=receipt_id,
        request_binding=request_binding,
        route_capability=route_capability,
        effect_kind="api_proposal_decision_scaffold_revision",
        expected_actor=expected_actor,
    )
    if context.get("attester") != authoritative_actor_id_from_binding(expected_actor):
        raise IdentityMutationError("scaffold revision actor differs from authenticated actor")

    return (candidate_ref, candidate_proposal, candidate_receipt)


def _reconcile_scaffold_revision_identity_mutation(
    mutation_path: Path,
    *,
    mutation: dict[str, Any],
    receipt_id: str,
    request_binding: dict[str, Any],
    proposal_id: str,
    engine: Engine,
    receipt_root: Path,
    reconciled_by: str,
    reason: str,
) -> dict[str, Any]:
    _require_unqueried_route_target(request_binding)
    mutation_ref = identity_mutation_source_ref(receipt_id)

    with Session(engine) as session:
        current_proposal = session.get(
            Proposal,
            proposal_id,
        )
        indexes = list(
            session.exec(
                select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
            ).all()
        )

    if current_proposal is None:
        raise IdentityMutationError("scaffold proposal no longer exists")

    # Phase 1 — candidate search: ReceiptIndex.refs can carry inherited
    # mutation_refs from earlier revisions and is **not** proof of exact
    # effect identity.  Candidates that merely inherit the mutation_ref
    # without claiming it in their revision_context are skipped below.
    candidates = [index for index in indexes if mutation_ref in list(index.refs or [])]

    if not candidates:
        raise IdentityMutationError(
            "verified scaffold revision receipt not found; mutation remains pending"
        )

    # Phase 2 — exact revision_context matching.
    exact_matches: list[tuple[str, Proposal, dict[str, Any]]] = []

    for candidate in candidates:
        result = _validate_scaffold_candidate_revision(
            candidate.path,
            receipt_id=receipt_id,
            request_binding=request_binding,
            proposal_id=proposal_id,
            receipt_root=receipt_root,
            mutation_ref=mutation_ref,
            expected_actor=mutation.get("actor"),
            route_capability=mutation.get("route_capability"),
        )
        if result is not None:
            exact_matches.append(result)

    if not exact_matches:
        raise IdentityMutationError(
            "verified scaffold revision receipt not found; mutation remains pending"
        )

    if len(exact_matches) > 1:
        raise IdentityMutationError("multiple scaffold revisions are bound to one mutation receipt")

    receipt_ref, proposal, receipt = exact_matches[0]
    context = receipt.get("revision_context", {})
    previous_receipt_ref = context.get("previous_receipt_ref")
    changed_fields = context.get("changed_scaffold_fields", [])

    response = ProposalScaffoldRevisionResponse(
        proposal=proposal,
        receipt_ref=receipt_ref,
        previous_receipt_ref=(previous_receipt_ref),
        changed_scaffold_fields=tuple(changed_fields),
        execution_allowed=False,
    )

    evidence_refs = [
        mutation_ref,
        receipt_ref,
    ]
    if previous_receipt_ref:
        evidence_refs.append(previous_receipt_ref)

    return _record_typed_reconciliation(
        mutation_path,
        mutation=mutation,
        resolver_id=(_SCAFFOLD_REVISION_RECONCILIATION_RESOLVER),
        reconciled_by=reconciled_by,
        reason=reason,
        evidence_refs=evidence_refs,
        domain_effect={
            "kind": "proposal_scaffold_revision",
            "proposal_id": proposal_id,
            "receipt_ref": receipt_ref,
            "previous_receipt_ref": (previous_receipt_ref),
            "changed_scaffold_fields": (changed_fields),
            "receipt_sha256": (_domain_receipt_sha256(receipt)),
            "canonical_resource": (f"/proposals/{proposal_id}/revisions"),
            "execution_allowed": False,
        },
        response=response,
    )


def _review_event_content_hash_from_row(
    event: ReviewEvent,
    *,
    proposal_receipt_ref: str,
    receipt_ref: str,
) -> str:
    if len(event.source_refs) < 2:
        raise IdentityMutationError("review event source refs are incomplete")

    if event.source_refs[0] != proposal_receipt_ref or event.source_refs[1] != receipt_ref:
        raise IdentityMutationError("review event generated source refs do not match its receipt")

    original_source_refs = event.source_refs[2:]
    core = {
        "proposal_id": event.proposal_id,
        "kind": event.kind,
        "attester": event.attester,
        "reason": event.reason,
        "text": event.text,
        "attestation_ref": (event.attestation_ref),
        "compare_with": event.compare_with,
        "source_refs": original_source_refs,
        "created_at_utc": (event.created_at_utc),
    }

    return hashlib.sha256(
        json.dumps(
            core,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _reconcile_review_event_identity_mutation(
    mutation_path: Path,
    *,
    mutation: dict[str, Any],
    receipt_id: str,
    request_binding: dict[str, Any],
    proposal_id: str,
    engine: Engine,
    receipt_root: Path,
    reconciled_by: str,
    reason: str,
) -> dict[str, Any]:
    _require_unqueried_route_target(request_binding)
    mutation_ref = identity_mutation_source_ref(receipt_id)

    with Session(engine) as session:
        current_proposal = session.get(
            Proposal,
            proposal_id,
        )
        events = list(
            session.exec(select(ReviewEvent).where(ReviewEvent.proposal_id == proposal_id)).all()
        )

    if current_proposal is None:
        raise IdentityMutationError("review-event proposal no longer exists")

    event = _single_bound_effect(
        events,
        mutation_ref=mutation_ref,
        label="review event",
    )

    receipt_ref = _receipt_ref_from_source_refs(
        event.source_refs,
        directory="review-events",
    )
    _path, receipt = _load_typed_domain_receipt(
        receipt_ref,
        receipt_root=receipt_root,
        expected_directory="review-events",
    )

    if receipt.get("kind") != ("state_core_review_event"):
        raise IdentityMutationError("domain receipt is not a review-event receipt")

    if receipt.get("review_event") != event.model_dump(mode="json"):
        raise IdentityMutationError("review-event row and receipt do not match")

    if receipt.get("proposal_id") != proposal_id:
        raise IdentityMutationError("review-event receipt proposal id does not match the route")

    _require_exact_domain_binding(
        receipt.get("mutation_context"),
        receipt_id=receipt_id,
        request_binding=request_binding,
        route_capability=mutation.get("route_capability"),
        effect_kind="api_review_event_create",
        expected_actor=mutation.get("actor"),
    )
    expected_actor_id = authoritative_actor_id_from_binding(mutation.get("actor"))
    if event.attester != expected_actor_id:
        raise IdentityMutationError("review-event row actor differs from authenticated actor")

    proposal_receipt_ref = receipt.get("proposal_receipt_ref")
    if not isinstance(
        proposal_receipt_ref,
        str,
    ):
        raise IdentityMutationError("review-event receipt has no proposal receipt ref")

    expected_content_hash = _review_event_content_hash_from_row(
        event,
        proposal_receipt_ref=(proposal_receipt_ref),
        receipt_ref=receipt_ref,
    )

    if event.content_hash != expected_content_hash:
        raise IdentityMutationError("review-event content hash does not match its row")

    response = ReviewEventCreateResponse(
        review_event=event,
        receipt_ref=receipt_ref,
        execution_allowed=False,
    )

    return _record_typed_reconciliation(
        mutation_path,
        mutation=mutation,
        resolver_id=(_REVIEW_EVENT_CREATE_RECONCILIATION_RESOLVER),
        reconciled_by=reconciled_by,
        reason=reason,
        evidence_refs=[
            mutation_ref,
            receipt_ref,
            proposal_receipt_ref,
        ],
        domain_effect={
            "kind": "review_event_create",
            "review_event_id": (event.review_event_id),
            "proposal_id": proposal_id,
            "content_hash": event.content_hash,
            "receipt_ref": receipt_ref,
            "receipt_sha256": (_domain_receipt_sha256(receipt)),
            "canonical_resource": (f"/proposals/{proposal_id}/timeline"),
            "execution_allowed": False,
        },
        response=response,
    )


def _dispatch_proposal_create(
    mutation_path: Path,
    *,
    mutation: dict[str, Any],
    receipt_id: str,
    request_binding: dict[str, Any],
    proposal_id: str | None,
    engine: Engine,
    receipt_root: Path,
    reconciled_by: str,
    reason: str,
) -> dict[str, Any]:
    del mutation, receipt_id, request_binding
    if proposal_id is not None:
        raise IdentityMutationError("Proposal create capability cannot bind a proposal id")
    return reconcile_proposal_create_identity_mutation(
        mutation_path,
        engine=engine,
        receipt_root=receipt_root,
        reconciled_by=reconciled_by,
        reason=reason,
    )


def _dispatch_attestation_create(
    mutation_path: Path,
    *,
    mutation: dict[str, Any],
    receipt_id: str,
    request_binding: dict[str, Any],
    proposal_id: str | None,
    engine: Engine,
    receipt_root: Path,
    reconciled_by: str,
    reason: str,
) -> dict[str, Any]:
    if proposal_id is None:
        raise IdentityMutationError("attestation resolver requires a proposal id")
    return _reconcile_attestation_identity_mutation(
        mutation_path,
        mutation=mutation,
        receipt_id=receipt_id,
        request_binding=request_binding,
        proposal_id=proposal_id,
        engine=engine,
        receipt_root=receipt_root,
        reconciled_by=reconciled_by,
        reason=reason,
    )


def _dispatch_scaffold_revision(
    mutation_path: Path,
    *,
    mutation: dict[str, Any],
    receipt_id: str,
    request_binding: dict[str, Any],
    proposal_id: str | None,
    engine: Engine,
    receipt_root: Path,
    reconciled_by: str,
    reason: str,
) -> dict[str, Any]:
    if proposal_id is None:
        raise IdentityMutationError("scaffold resolver requires a proposal id")
    return _reconcile_scaffold_revision_identity_mutation(
        mutation_path,
        mutation=mutation,
        receipt_id=receipt_id,
        request_binding=request_binding,
        proposal_id=proposal_id,
        engine=engine,
        receipt_root=receipt_root,
        reconciled_by=reconciled_by,
        reason=reason,
    )


def _dispatch_review_event_create(
    mutation_path: Path,
    *,
    mutation: dict[str, Any],
    receipt_id: str,
    request_binding: dict[str, Any],
    proposal_id: str | None,
    engine: Engine,
    receipt_root: Path,
    reconciled_by: str,
    reason: str,
) -> dict[str, Any]:
    if proposal_id is None:
        raise IdentityMutationError("review-event resolver requires a proposal id")
    return _reconcile_review_event_identity_mutation(
        mutation_path,
        mutation=mutation,
        receipt_id=receipt_id,
        request_binding=request_binding,
        proposal_id=proposal_id,
        engine=engine,
        receipt_root=receipt_root,
        reconciled_by=reconciled_by,
        reason=reason,
    )


_IDENTITY_MUTATION_RECONCILIATION_CONTRACTS = (
    IdentityMutationResolverContract(
        capability_id="finharness.api.proposals.create.keyed.v1",
        resolver_id=_PROPOSAL_CREATE_RECONCILIATION_RESOLVER,
        method="POST",
        canonical_path_template="/proposals",
        handler=_dispatch_proposal_create,
    ),
    IdentityMutationResolverContract(
        capability_id="finharness.api.proposals.attest.keyed.v1",
        resolver_id=_ATTESTATION_CREATE_RECONCILIATION_RESOLVER,
        method="POST",
        canonical_path_template="/proposals/{proposal_id}/attest",
        handler=_dispatch_attestation_create,
    ),
    IdentityMutationResolverContract(
        capability_id="finharness.api.proposals.scaffold-revision.keyed.v1",
        resolver_id=_SCAFFOLD_REVISION_RECONCILIATION_RESOLVER,
        method="PATCH",
        canonical_path_template="/proposals/{proposal_id}/decision-scaffold",
        handler=_dispatch_scaffold_revision,
    ),
    IdentityMutationResolverContract(
        capability_id="finharness.api.proposals.review-event.keyed.v1",
        resolver_id=_REVIEW_EVENT_CREATE_RECONCILIATION_RESOLVER,
        method="POST",
        canonical_path_template="/proposals/{proposal_id}/review-events",
        handler=_dispatch_review_event_create,
    ),
)


def identity_mutation_reconciliation_dispatcher_contracts(
) -> tuple[IdentityMutationResolverContract, ...]:
    return _IDENTITY_MUTATION_RECONCILIATION_CONTRACTS


def _require_identity_mutation_resolver_contract(
    mutation: dict[str, Any],
    *,
    resolver_id: str,
    request_binding: dict[str, Any],
) -> IdentityMutationResolverContract:
    try:
        _by_route, by_resolver = identity_mutation_resolver_contract_maps(
            _IDENTITY_MUTATION_RECONCILIATION_CONTRACTS
        )
    except KeyedMutationCapabilityError as exc:
        raise IdentityMutationError(str(exc)) from exc
    contract = by_resolver.get(resolver_id)
    if contract is None:
        raise IdentityMutationError(
            "no typed reconciliation resolver for this capability"
        )

    method = request_binding.get("method")
    path = request_binding.get("path")
    if method != contract.method or not isinstance(path, str):
        raise IdentityMutationError(
            "mutation route differs from executable resolver contract"
        )
    route_regex, _path_format, _convertors = compile_path(
        contract.canonical_path_template
    )
    if route_regex.fullmatch(path) is None:
        raise IdentityMutationError(
            "mutation route differs from executable resolver contract"
        )
    if mutation.get("schema") == "finharness.api_mutation_identity_receipt.v2":
        binding = mutation.get("route_capability")
        if not isinstance(binding, dict):
            raise IdentityMutationError(
                "mutation route capability binding is missing"
            )
        if (
            binding.get("capability_id") != contract.capability_id
            or binding.get("resolver_id") != contract.resolver_id
            or binding.get("method") != contract.method
            or binding.get("canonical_path_template")
            != contract.canonical_path_template
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
) -> dict[str, Any]:
    """Dispatch one pending mutation to its typed resolver."""

    mutation_path = Path(receipt_path)
    mutation = load_identity_mutation_receipt(mutation_path)

    (
        receipt_id,
        request_binding,
        resolver_id,
        proposal_id,
    ) = _require_pending_mutation_route(mutation)

    contract = _require_identity_mutation_resolver_contract(
        mutation,
        resolver_id=resolver_id,
        request_binding=request_binding,
    )
    return contract.handler(
        mutation_path,
        mutation=mutation,
        receipt_id=receipt_id,
        request_binding=request_binding,
        proposal_id=proposal_id,
        engine=engine,
        receipt_root=Path(receipt_root),
        reconciled_by=reconciled_by,
        reason=reason,
    )


class AttestationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: DecisionInput
    reason: str
    expected_proposal_version_id: str
    expected_proposal_receipt_ref: str
    source_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "reason",
        "expected_proposal_version_id",
        "expected_proposal_receipt_ref",
    )
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("this field is required and must not be blank")
        return value


class AttestationCreateResponse(BaseModel):
    attestation: Attestation
    proposal: Proposal
    receipt_ref: str
    admitted_proposal_version: ProposalVersionView
    approved_is_not_execution_authorization: bool = True
    execution_allowed: bool = False


class ProposalVersionView(BaseModel):
    proposal_id: str
    proposal_version_id: str
    receipt_ref: str


class AttestationReviewView(BaseModel):
    attestation_id: str
    proposal_id: str
    attester: str
    reason: str
    decision: DecisionInput
    source_refs: list[str]
    authority_level: str
    created_at_utc: str
    bound_proposal_version_id: str | None
    bound_proposal_receipt_ref: str | None
    stale: bool


class AgentReviewSurface(BaseModel):
    created_by: Literal["agent"] = "agent"
    active_profile: str
    reason: str
    context_pack_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    receipt_ref: str
    review_state: Literal["pending_human_review", "human_attestation_recorded"]
    requires_human_review: bool = True
    execution_allowed: bool = False
    authority_transition: bool = False
    guardrails: dict[str, Any] = Field(
        default_factory=lambda: {
            "execution_allowed": False,
            "requires_human_review": True,
            "not_approval": True,
            "not_attestation": True,
            "not_execution_authorization": True,
        }
    )
    non_claims: tuple[str, ...] = (
        "Agent-created proposals are review drafts, not recommendations.",
        "Human review is required before any decision of record.",
        "Agent draft provenance is review metadata, not approval or execution.",
    )


class ProposalReviewResponse(BaseModel):
    proposal: Proposal
    attestations: list[AttestationReviewView]
    open_for_review: bool
    agent_review: AgentReviewSurface | None = None
    queue_checks: ProposalQueueChecks
    non_claims: tuple[str, ...] = (
        "Proposal is review evidence only.",
        "Human attestation is not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


ReviewTaskState = Literal[
    "ready_for_review",
    "needs_evidence",
    "blocked",
    "completed",
    "archived",
]


class EvidenceRequest(BaseModel):
    request_id: str
    code: str
    status: Literal["open"] = "open"
    message: str
    recovery_hint: str
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    blocked_transitions: tuple[str, ...] = ()
    execution_allowed: bool = False
    authority_transition: bool = False


class ReviewTaskLifecycle(BaseModel):
    task_id: str
    proposal_id: str
    state: ReviewTaskState
    created_by: Literal["agent", "human_or_system"]
    active_profile: str | None = None
    open_for_review: bool
    is_archived: bool
    queue_check_state: str
    block_codes: list[str] = Field(default_factory=list)
    blocked_transitions: tuple[str, ...] = ()
    evidence_requests: list[EvidenceRequest] = Field(default_factory=list)
    latest_event_kind: str | None = None
    latest_event_at_utc: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    context_pack_refs: list[str] = Field(default_factory=list)
    requires_human_review: bool = True
    execution_allowed: bool = False
    authority_transition: bool = False
    non_claims: tuple[str, ...] = (
        "Review task lifecycle is a read-only projection, not a new task write surface.",
        "Evidence requests are derived from queue checks; they are not approval.",
        "Review task state does not authorize execution.",
    )


class ProposalRevision(BaseModel):
    receipt_id: str
    receipt_ref: str
    created_at_utc: str
    content_hash: str | None = None
    supersedes: str | None = None
    proposal: dict[str, Any] = Field(default_factory=dict)
    revision_context: dict[str, Any] = Field(default_factory=dict)
    execution_allowed: bool = False


class ProposalRevisionResponse(BaseModel):
    proposal_id: str
    revisions: list[ProposalRevision]
    non_claims: tuple[str, ...] = (
        "Proposal revisions are historical evidence only.",
        "Revision history is not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


class ProposalScaffoldRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    decision_scaffold: dict[str, Any]
    expected_proposal_version_id: str
    expected_proposal_receipt_ref: str
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("reason", "expected_proposal_version_id", "expected_proposal_receipt_ref")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("this field is required and must not be blank")
        return value


class ProposalScaffoldRevisionResponse(BaseModel):
    proposal: Proposal
    receipt_ref: str
    previous_receipt_ref: str | None
    changed_scaffold_fields: tuple[str, ...]
    admitted_proposal_version: ProposalVersionView
    resulting_proposal_version: ProposalVersionView
    non_claims: tuple[str, ...] = (
        "Proposal scaffold revisions are historical review evidence.",
        "Counter-evidence enables human confirmation checks; it is not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


class ScaffoldRevisionCandidateApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    human_reason: str
    expected_proposal_version_id: str
    expected_candidate_receipt_ref: str
    expected_proposal_receipt_ref: str
    expected_preflight_report_hash: str
    explicit_confirmation: bool
    explicit_preflight_acknowledgement: bool = False
    acknowledged_preflight_warning_codes: list[str] = Field(default_factory=list)

    @field_validator(
        "human_reason",
        "expected_proposal_version_id",
        "expected_candidate_receipt_ref",
        "expected_proposal_receipt_ref",
        "expected_preflight_report_hash",
    )
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "candidate apply requires non-blank human context, receipts, and preflight hash"
            )
        return value

    @field_validator("explicit_confirmation")
    @classmethod
    def require_explicit_confirmation(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("candidate apply requires explicit_confirmation=true")
        return True

    @field_validator("acknowledged_preflight_warning_codes")
    @classmethod
    def clean_warning_codes(cls, value: list[str]) -> list[str]:
        return sorted({str(item).strip() for item in value if str(item).strip()})


class ScaffoldRevisionCandidateApplyResponse(BaseModel):
    proposal: Proposal
    receipt_ref: str
    previous_receipt_ref: str | None
    changed_scaffold_fields: tuple[str, ...]
    admitted_proposal_version: ProposalVersionView
    resulting_proposal_version: ProposalVersionView
    applied_candidate_id: str
    candidate_receipt_ref: str
    candidate_review_event_id: str
    non_claims: tuple[str, ...] = (
        "Candidate apply is a human-confirmed scaffold revision, not Agent auto-apply.",
        "Applying scaffold text is not approval, attestation, or execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False
    authority_transition: bool = False


class ScaffoldCandidatePreflightFindingView(BaseModel):
    code: str
    severity: str
    message: str
    recovery_hint: str
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    blocks_apply: bool


class ScaffoldCandidatePreflightResponse(BaseModel):
    candidate_id: str
    proposal_id: str
    status: str
    system_preflight_recomputed: bool
    findings: list[ScaffoldCandidatePreflightFindingView]
    candidate_receipt_ref: str | None
    current_proposal_receipt_ref: str | None
    proposed_scaffold: dict[str, Any]
    changed_fields: list[str]
    basis_risk_ids: list[str]
    active_basis_risk_ids: list[str]
    missing_basis_risk_ids: list[str]
    source_refs: list[str]
    receipt_refs: list[str]
    report_hash: str
    non_claims: tuple[str, ...] = SCAFFOLD_CANDIDATE_PREFLIGHT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


def _proposal_attestations(
    proposal_id: str,
    *,
    session: Session,
) -> list[Attestation]:
    return list(
        session.exec(
            select(Attestation)
            .where(Attestation.proposal_id == proposal_id)
            .order_by(desc(Attestation.created_at_utc), desc(Attestation.attestation_id))
        ).all()
    )


# Anomaly codes from the shared walker default to a 500 (a corrupt chain is a
# server-side data problem); these are the exceptions surfaced as 404.
_REVISION_ANOMALY_STATUS: dict[str, int] = {
    "missing": 404,
    "outside_allowed_roots": 404,
}


def _scaffold_patch_from_candidate(
    *,
    event: ReviewEvent,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if payload.get("proposal_id") != event.proposal_id:
        raise ValueError("candidate payload proposal_id does not match review event")
    patch = payload.get("scaffold_patch")
    if not isinstance(patch, dict):
        raise ValueError("candidate payload scaffold_patch is not an object")
    return patch


def _preflight_finding_view(
    finding: PreflightFinding,
) -> ScaffoldCandidatePreflightFindingView:
    return ScaffoldCandidatePreflightFindingView(
        code=finding.code,
        severity=finding.severity,
        message=finding.message,
        recovery_hint=finding.recovery_hint,
        source_refs=finding.source_refs,
        receipt_refs=finding.receipt_refs,
        blocks_apply=finding.blocks_apply,
    )


def _preflight_warning_codes(findings: list[PreflightFinding]) -> set[str]:
    return {finding.code for finding in findings if not finding.blocks_apply}


def _enforce_scaffold_candidate_preflight_gate(
    candidate_id: str,
    *,
    request: ScaffoldRevisionCandidateApplyRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ScaffoldCandidatePreflightReport:
    preflight = preflight_scaffold_revision_candidate(
        candidate_id,
        engine=engine,
        receipt_root=receipt_root,
    )
    if preflight is None:
        raise HTTPException(
            status_code=404,
            detail=f"scaffold revision candidate not found: {candidate_id}",
        )
    if preflight.report_hash != request.expected_preflight_report_hash.strip():
        raise HTTPException(
            status_code=409,
            detail="preflight report hash does not match current system preflight",
        )
    if preflight.status == "block":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "preflight_blocked",
                "findings": [
                    _preflight_finding_view(finding).model_dump() for finding in preflight.findings
                ],
                "execution_allowed": False,
                "authority_transition": False,
            },
        )
    warning_codes = _preflight_warning_codes(preflight.findings)
    if warning_codes:
        acknowledged = set(request.acknowledged_preflight_warning_codes)
        if not request.explicit_preflight_acknowledgement:
            raise HTTPException(
                status_code=422,
                detail="preflight warnings require explicit acknowledgement",
            )
        if not warning_codes <= acknowledged:
            raise HTTPException(
                status_code=422,
                detail="not all preflight warnings acknowledged",
            )
    return preflight


def _proposal_revision_chain(
    proposal: Proposal,
    *,
    receipt_root: Path,
    max_revisions: int = 100,
) -> list[ProposalRevision]:
    walk = walk_proposal_revisions(
        proposal.proposal_id,
        proposal.receipt_ref,
        allowed_roots=(ROOT.resolve(), receipt_root.resolve()),
        max_revisions=max_revisions,
    )
    for anomaly in walk.anomalies:
        if anomaly.code == "no_receipt_ref":
            # No receipt yet just means no history to show, not an error.
            continue
        raise HTTPException(
            status_code=_REVISION_ANOMALY_STATUS.get(anomaly.code, 500),
            detail=anomaly.detail,
        )
    return [
        ProposalRevision(
            receipt_id=record.receipt_id,
            receipt_ref=record.receipt_ref,
            created_at_utc=record.created_at_utc,
            content_hash=record.content_hash,
            supersedes=record.supersedes,
            proposal=record.proposal,
            revision_context=record.revision_context,
            execution_allowed=False,
        )
        for record in walk.revisions
    ]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _agent_review_surface(
    proposal: Proposal,
    *,
    receipt_root: Path,
    open_for_review: bool,
) -> AgentReviewSurface | None:
    walk = walk_proposal_revisions(
        proposal.proposal_id,
        proposal.receipt_ref,
        allowed_roots=(ROOT.resolve(), receipt_root.resolve()),
        max_revisions=100,
    )
    for record in walk.revisions:
        context = record.revision_context
        if context.get("kind") != "agent_proposal_draft":
            continue
        return AgentReviewSurface(
            active_profile=str(context.get("profile") or "unknown"),
            reason=str(context.get("reason") or ""),
            context_pack_refs=_string_list(context.get("context_pack_refs")),
            source_refs=_string_list(record.proposal.get("source_refs")),
            receipt_ref=record.receipt_ref,
            review_state=(
                "pending_human_review" if open_for_review else "human_attestation_recorded"
            ),
            requires_human_review=True,
            execution_allowed=False,
            authority_transition=False,
        )
    return None


def _proposal_review_response(
    proposal: Proposal,
    attestations: list[Attestation],
    *,
    engine: EngineDependency,
    receipt_root: Path,
) -> ProposalReviewResponse:
    current = _resolve_proposal_version_for_api(
        proposal.proposal_id,
        engine=engine,
        receipt_root=receipt_root,
    )
    views = _attestation_review_views(attestations, current=current)
    open_for_review = not any(
        not attestation.stale and attestation.decision in {"approved", "rejected"}
        for attestation in views
    )
    agent_review = _agent_review_surface(
        proposal,
        receipt_root=receipt_root,
        open_for_review=open_for_review,
    )
    return ProposalReviewResponse(
        proposal=proposal,
        attestations=views,
        open_for_review=open_for_review,
        agent_review=agent_review,
        queue_checks=build_proposal_queue_checks(
            proposal,
            engine=engine,
            open_for_review=open_for_review,
            created_by="agent" if agent_review else "human_or_system",
            active_profile=agent_review.active_profile if agent_review else None,
            source_refs=list(proposal.source_refs),
            receipt_refs=[proposal.receipt_ref] if proposal.receipt_ref else [],
            context_pack_refs=agent_review.context_pack_refs if agent_review else [],
        ),
        execution_allowed=False,
    )


def _resolve_proposal_version_for_api(
    proposal_id: str,
    *,
    engine: EngineDependency,
    receipt_root: Path,
) -> CurrentProposalVersion:
    try:
        return resolve_current_proposal_version(
            proposal_id,
            engine=engine,
            receipt_root=receipt_root,
        )
    except ProposalVersionResolutionError as exc:
        status = 404 if exc.code == "proposal_not_found" else 409
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc


def _attestation_review_views(
    attestations: list[Attestation],
    *,
    current: CurrentProposalVersion,
) -> list[AttestationReviewView]:
    lineage_by_receipt = {item.receipt_ref: item for item in current.lineage}
    views: list[AttestationReviewView] = []
    for attestation in attestations:
        bound = next(
            (
                lineage_by_receipt[ref]
                for ref in attestation.source_refs
                if ref in lineage_by_receipt
            ),
            None,
        )
        views.append(
            AttestationReviewView(
                **attestation.model_dump(mode="json"),
                bound_proposal_version_id=(
                    bound.proposal_version_id if bound is not None else None
                ),
                bound_proposal_receipt_ref=(bound.receipt_ref if bound is not None else None),
                stale=(bound is None or bound.proposal_version_id != current.proposal_version_id),
            )
        )
    return views


_EVIDENCE_REQUEST_CODES = {
    "missing_source_refs",
    "counter_evidence_needed",
    "data_gap",
    "stale_context",
    "policy_mismatch",
}


def _review_task_lifecycle(
    review: ProposalReviewResponse,
    *,
    timeline: ProposalTimelineResponse,
) -> ReviewTaskLifecycle:
    queue_checks = review.queue_checks
    evidence_requests = [
        EvidenceRequest(
            request_id=f"evidence_request:{review.proposal.proposal_id}:{finding.code}",
            code=finding.code,
            message=finding.message,
            recovery_hint=finding.recovery_hint,
            source_refs=list(finding.source_refs),
            receipt_refs=list(finding.receipt_refs),
            blocked_transitions=tuple(finding.blocked_transitions),
            execution_allowed=False,
            authority_transition=False,
        )
        for finding in queue_checks.blocks
        if finding.code in _EVIDENCE_REQUEST_CODES
    ]
    latest = timeline.entries[0] if timeline.entries else None
    non_evidence_blocks = [
        finding.code
        for finding in queue_checks.blocks
        if finding.code not in _EVIDENCE_REQUEST_CODES and finding.code != "human_review_required"
    ]
    if timeline.is_archived:
        state: ReviewTaskState = "archived"
    elif not review.open_for_review:
        state = "completed"
    elif evidence_requests:
        state = "needs_evidence"
    elif non_evidence_blocks:
        state = "blocked"
    else:
        state = "ready_for_review"
    return ReviewTaskLifecycle(
        task_id=f"review_task:{review.proposal.proposal_id}",
        proposal_id=review.proposal.proposal_id,
        state=state,
        created_by=queue_checks.created_by,
        active_profile=queue_checks.active_profile,
        open_for_review=review.open_for_review,
        is_archived=timeline.is_archived,
        queue_check_state=queue_checks.check_state,
        block_codes=[finding.code for finding in queue_checks.blocks],
        blocked_transitions=queue_checks.blocked_transitions,
        evidence_requests=evidence_requests,
        latest_event_kind=latest.kind if latest else None,
        latest_event_at_utc=latest.created_at_utc if latest else None,
        source_refs=list(queue_checks.source_refs),
        receipt_refs=list(queue_checks.receipt_refs),
        context_pack_refs=list(queue_checks.context_pack_refs),
        requires_human_review=True,
        execution_allowed=False,
        authority_transition=False,
    )


@router.get("/proposals", response_model=list[ProposalReviewResponse])
async def list_proposals(
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    status: Annotated[Literal["all", "open", "attested"], Query()] = "all",
    archive: Annotated[Literal["all", "active", "archived"], Query()] = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ProposalReviewResponse]:
    # `archive` defaults to "all": the legacy response (contents + shape) is unchanged.
    # Only an explicit archive=active|archived hides/keeps archived proposals; archive
    # events never silently change the default list.
    with Session(engine) as session:
        proposals = list(
            session.exec(
                select(Proposal)
                .order_by(desc(Proposal.created_at_utc), desc(Proposal.proposal_id))
                .limit(limit)
            ).all()
        )
        responses: list[ProposalReviewResponse] = []
        for proposal in proposals:
            attestations = _proposal_attestations(proposal.proposal_id, session=session)
            responses.append(
                _proposal_review_response(
                    proposal,
                    attestations,
                    engine=engine,
                    receipt_root=receipt_root,
                )
            )
    if status == "open":
        responses = [response for response in responses if response.open_for_review]
    elif status == "attested":
        responses = [response for response in responses if not response.open_for_review]
    if archive != "all":
        archived = archived_proposal_ids(engine)
        if archive == "active":
            responses = [r for r in responses if r.proposal.proposal_id not in archived]
        else:  # archived
            responses = [r for r in responses if r.proposal.proposal_id in archived]
    return responses


@router.get("/proposals/{proposal_id}", response_model=ProposalReviewResponse)
async def get_proposal(
    proposal_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ProposalReviewResponse:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        if proposal is None:
            raise HTTPException(
                status_code=404,
                detail=f"proposal not found: {proposal_id}",
            )
        attestations = _proposal_attestations(proposal_id, session=session)
    return _proposal_review_response(
        proposal,
        attestations,
        engine=engine,
        receipt_root=receipt_root,
    )


@router.get(
    "/proposals/{proposal_id}/queue-checks",
    response_model=ProposalQueueChecks,
)
async def get_proposal_queue_checks(
    proposal_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ProposalQueueChecks:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        if proposal is None:
            raise HTTPException(
                status_code=404,
                detail=f"proposal not found: {proposal_id}",
            )
        attestations = _proposal_attestations(proposal_id, session=session)
    return _proposal_review_response(
        proposal,
        attestations,
        engine=engine,
        receipt_root=receipt_root,
    ).queue_checks


@router.get(
    "/proposals/{proposal_id}/review-task",
    response_model=ReviewTaskLifecycle,
)
async def get_proposal_review_task(
    proposal_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ReviewTaskLifecycle:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        if proposal is None:
            raise HTTPException(
                status_code=404,
                detail=f"proposal not found: {proposal_id}",
            )
        attestations = _proposal_attestations(proposal_id, session=session)
    timeline = read_proposal_timeline(engine, proposal_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail=f"proposal not found: {proposal_id}")
    review = _proposal_review_response(
        proposal,
        attestations,
        engine=engine,
        receipt_root=receipt_root,
    )
    return _review_task_lifecycle(
        review,
        timeline=ProposalTimelineResponse(
            proposal_id=timeline.proposal_id,
            is_archived=timeline.is_archived,
            entries=[
                TimelineEntry(
                    source_type=entry.source_type,
                    id=entry.id,
                    kind=entry.kind,
                    created_at_utc=entry.created_at_utc,
                    attester=entry.attester,
                    reason=entry.reason,
                    detail=entry.detail,
                )
                for entry in timeline.entries
            ],
            execution_allowed=False,
        ),
    )


@router.get("/proposals/{proposal_id}/revisions", response_model=ProposalRevisionResponse)
async def get_proposal_revisions(
    proposal_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ProposalRevisionResponse:
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail=f"proposal not found: {proposal_id}",
        )
    return ProposalRevisionResponse(
        proposal_id=proposal.proposal_id,
        revisions=_proposal_revision_chain(proposal, receipt_root=receipt_root),
        execution_allowed=False,
    )


@router.patch(
    "/proposals/{proposal_id}/decision-scaffold",
    response_model=ProposalScaffoldRevisionResponse,
)
async def revise_proposal_decision_scaffold(
    proposal_id: str,
    request: ProposalScaffoldRevisionRequest,
    http_request: Request,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    operator: WriteCapabilityDependency,
) -> ProposalScaffoldRevisionResponse:
    binding = _route_identity_mutation_binding(
        http_request,
        effect_kind=("api_proposal_decision_scaffold_revision"),
        operator=operator,
    )
    source_refs = list(request.source_refs)
    mutation_context: dict[str, Any] | None = None

    if binding is not None:
        mutation_ref, mutation_context = binding
        if mutation_ref not in source_refs:
            source_refs.append(mutation_ref)

    try:
        from finharness.statecore.proposal_version import ProposalVersionExpectation

        expectation = ProposalVersionExpectation(
            proposal_id=proposal_id,
            proposal_version_id=request.expected_proposal_version_id.strip(),
            receipt_ref=request.expected_proposal_receipt_ref.strip(),
        )
        result = revise_governed_proposal_scaffold(
            proposal_id=proposal_id,
            scaffold_patch=request.decision_scaffold,
            attester=operator.authoritative_actor_id,
            reason=request.reason.strip(),
            expectation=expectation,
            source_refs=source_refs,
            revision_context_extra=mutation_context,
            engine=engine,
            receipt_root=receipt_root,
        )
    except ProposalVersionResolutionError as exc:
        status = 404 if exc.code == "proposal_not_found" else 409
        detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
        if exc.code in ("proposal_version_conflict", "stale_expected_version", "stale_expected_receipt"):  # noqa: E501
            detail["proposal_id"] = proposal_id
            detail["execution_allowed"] = False
        raise HTTPException(status_code=status, detail=detail) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"proposal not found: {proposal_id}",
        ) from exc
    except (DecisionScaffoldError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ProposalScaffoldRevisionResponse(
        proposal=result.proposal,
        receipt_ref=result.receipt_ref,
        previous_receipt_ref=result.previous_receipt_ref,
        changed_scaffold_fields=result.changed_scaffold_fields,
        admitted_proposal_version=ProposalVersionView(
            proposal_id=proposal_id,
            proposal_version_id=result.admitted_proposal_version_id,
            receipt_ref=result.admitted_proposal_receipt_ref,
        ),
        resulting_proposal_version=ProposalVersionView(
            proposal_id=proposal_id,
            proposal_version_id=result.resulting_proposal_version_id,
            receipt_ref=result.resulting_proposal_receipt_ref,
        ),
        execution_allowed=False,
    )


@router.get(
    "/scaffold-revision-candidates/{candidate_id}/preflight",
    response_model=ScaffoldCandidatePreflightResponse,
)
async def get_scaffold_revision_candidate_preflight(
    candidate_id: str,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ScaffoldCandidatePreflightResponse:
    report = preflight_scaffold_revision_candidate(
        candidate_id,
        engine=engine,
        receipt_root=receipt_root,
    )
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"scaffold revision candidate not found: {candidate_id}",
        )
    return ScaffoldCandidatePreflightResponse(
        candidate_id=report.candidate_id,
        proposal_id=report.proposal_id,
        status=report.status,
        system_preflight_recomputed=report.system_preflight_recomputed,
        findings=[_preflight_finding_view(finding) for finding in report.findings],
        candidate_receipt_ref=report.candidate_receipt_ref,
        current_proposal_receipt_ref=report.current_proposal_receipt_ref,
        proposed_scaffold=report.proposed_scaffold,
        changed_fields=report.changed_fields,
        basis_risk_ids=report.basis_risk_ids,
        active_basis_risk_ids=report.active_basis_risk_ids,
        missing_basis_risk_ids=report.missing_basis_risk_ids,
        source_refs=report.source_refs,
        receipt_refs=report.receipt_refs,
        report_hash=report.report_hash,
        execution_allowed=False,
        authority_transition=False,
    )


@router.post(
    "/scaffold-revision-candidates/{candidate_id}/apply",
    response_model=ScaffoldRevisionCandidateApplyResponse,
)
async def apply_scaffold_revision_candidate(
    candidate_id: str,
    request: ScaffoldRevisionCandidateApplyRequest,
    http_request: Request,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    operator: WriteCapabilityDependency,
) -> ScaffoldRevisionCandidateApplyResponse:
    binding = _route_identity_mutation_binding(
        http_request,
        effect_kind="api_scaffold_revision_candidate_apply",
        operator=operator,
    )
    candidate = find_scaffold_revision_candidate(candidate_id, engine=engine)
    if candidate is None:
        raise HTTPException(
            status_code=404,
            detail=f"scaffold revision candidate not found: {candidate_id}",
        )
    event = candidate.event
    payload = candidate.payload
    if payload is None:
        raise HTTPException(
            status_code=422,
            detail=candidate.payload_error or "candidate payload is not an object",
        )
    candidate_receipt_ref = candidate.candidate_receipt_ref
    if not candidate_receipt_ref:
        raise HTTPException(
            status_code=422,
            detail="candidate review event receipt ref is missing",
        )
    if request.expected_candidate_receipt_ref.strip() != candidate_receipt_ref:
        raise HTTPException(
            status_code=409,
            detail="candidate receipt ref does not match expected_candidate_receipt_ref",
        )
    with Session(engine) as session:
        proposal = session.get(Proposal, event.proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=404,
            detail=f"proposal not found: {event.proposal_id}",
        )
    if request.expected_proposal_receipt_ref.strip() != (proposal.receipt_ref or ""):
        raise HTTPException(
            status_code=409,
            detail="proposal receipt ref does not match expected_proposal_receipt_ref",
        )
    # Also validate version identity
    from finharness.statecore.proposal_version import ProposalVersionExpectation

    expectation = ProposalVersionExpectation(
        proposal_id=event.proposal_id,
        proposal_version_id=request.expected_proposal_version_id.strip(),
        receipt_ref=request.expected_proposal_receipt_ref.strip(),
    )
    preflight = _enforce_scaffold_candidate_preflight_gate(
        candidate_id,
        request=request,
        engine=engine,
        receipt_root=receipt_root,
    )

    try:
        scaffold_patch = _scaffold_patch_from_candidate(event=event, payload=payload)
        result = revise_governed_proposal_scaffold(
            proposal_id=event.proposal_id,
            scaffold_patch=scaffold_patch,
            attester=operator.authoritative_actor_id,
            reason=request.human_reason.strip(),
            expectation=expectation,
            source_refs=[
                *([binding[0]] if binding is not None else []),
                candidate_receipt_ref,
                request.expected_proposal_receipt_ref.strip(),
                *event.source_refs,
                *_string_list(payload.get("source_refs")),
                *_string_list(payload.get("receipt_refs")),
            ],
            revision_context_extra={
                "source": "agent_scaffold_revision_apply_candidate",
                "candidate_id": candidate_id,
                "candidate_review_event_id": event.review_event_id,
                "candidate_receipt_ref": candidate_receipt_ref,
                "expected_proposal_receipt_ref": request.expected_proposal_receipt_ref.strip(),
                "system_preflight_report_hash": preflight.report_hash,
                "system_preflight_status": preflight.status,
                "system_preflight_recomputed": True,
                "system_preflight_finding_codes": [finding.code for finding in preflight.findings],
                "acknowledged_preflight_warning_codes": (
                    request.acknowledged_preflight_warning_codes
                ),
                "human_confirmed": True,
                "explicit_confirmation": True,
                "explicit_preflight_acknowledgement": (request.explicit_preflight_acknowledgement),
                "authority_transition": False,
                **(binding[1] if binding is not None else {}),
            },
            engine=engine,
            receipt_root=receipt_root,
        )
    except (DecisionScaffoldError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ScaffoldRevisionCandidateApplyResponse(
        proposal=result.proposal,
        receipt_ref=result.receipt_ref,
        previous_receipt_ref=result.previous_receipt_ref,
        changed_scaffold_fields=result.changed_scaffold_fields,
        admitted_proposal_version=ProposalVersionView(
            proposal_id=event.proposal_id,
            proposal_version_id=result.admitted_proposal_version_id,
            receipt_ref=result.admitted_proposal_receipt_ref,
        ),
        resulting_proposal_version=ProposalVersionView(
            proposal_id=event.proposal_id,
            proposal_version_id=result.resulting_proposal_version_id,
            receipt_ref=result.resulting_proposal_receipt_ref,
        ),
        applied_candidate_id=candidate_id,
        candidate_receipt_ref=candidate_receipt_ref,
        candidate_review_event_id=event.review_event_id,
        execution_allowed=False,
        authority_transition=False,
    )


@router.post("/proposals", response_model=ProposalCreateResponse)
async def create_proposal(
    request: ProposalCreateRequest,
    http_request: Request,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write_capability: WriteCapabilityDependency,
) -> ProposalCreateResponse:
    binding = _route_identity_mutation_binding(
        http_request,
        effect_kind="api_proposal_create",
    )

    source_refs = list(request.source_refs)
    proposal_id: str | None = None
    revision_context: dict[str, Any] | None = None
    idempotent = False

    if binding is not None:
        mutation_ref, mutation_context = binding
        if mutation_ref not in source_refs:
            source_refs.append(mutation_ref)

        mutation_receipt_id = mutation_context.get("identity_mutation_receipt_id")
        if isinstance(mutation_receipt_id, str) and mutation_receipt_id:
            proposal_id = proposal_id_for_identity_mutation(mutation_receipt_id)
        idempotent = True
        revision_context = {
            **mutation_context,
            "kind": "api_proposal_create",
        }

    try:
        result = create_governed_proposal(
            kind=request.kind.strip(),
            claim=request.claim.strip(),
            evidence=request.evidence,
            assumptions=request.assumptions,
            limitations=request.limitations,
            non_claims=request.non_claims,
            source_refs=source_refs,
            decision_scaffold=request.decision_scaffold,
            engine=engine,
            receipt_root=receipt_root,
            proposal_id=proposal_id,
            idempotent=idempotent,
            revision_context=revision_context,
        )
    except DecisionScaffoldError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ProposalCreateResponse.model_validate(
        proposal_create_response_payload(
            result.proposal,
            receipt_ref=result.receipt_ref,
        )
    )


@router.post("/proposals/{proposal_id}/attest", response_model=AttestationCreateResponse)
async def attest_proposal(
    proposal_id: str,
    request: AttestationCreateRequest,
    http_request: Request,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    operator: WriteCapabilityDependency,
) -> AttestationCreateResponse:
    binding = _route_identity_mutation_binding(
        http_request,
        effect_kind="api_attestation_create",
        operator=operator,
    )
    source_refs = list(request.source_refs)
    mutation_context: dict[str, Any] | None = None

    if binding is not None:
        mutation_ref, mutation_context = binding
        if mutation_ref not in source_refs:
            source_refs.append(mutation_ref)

    try:
        from finharness.statecore.proposal_version import ProposalVersionExpectation

        expectation = ProposalVersionExpectation(
            proposal_id=proposal_id,
            proposal_version_id=request.expected_proposal_version_id.strip(),
            receipt_ref=request.expected_proposal_receipt_ref.strip(),
        )
        result = create_governed_attestation(
            proposal_id=proposal_id,
            decision=request.decision,
            attester=operator.authoritative_actor_id,
            reason=request.reason.strip(),
            expectation=expectation,
            source_refs=source_refs,
            mutation_context=mutation_context,
            engine=engine,
            receipt_root=receipt_root,
        )
    except ProposalVersionResolutionError as exc:
        status = 404 if exc.code == "proposal_not_found" else 409
        detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
        if exc.code in ("proposal_version_conflict", "stale_expected_version", "stale_expected_receipt"):  # noqa: E501
            detail["proposal_id"] = proposal_id
            detail["execution_allowed"] = False
        raise HTTPException(
            status_code=status,
            detail=detail,
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"proposal not found: {proposal_id}",
        ) from exc
    except HighRiskConfirmationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return AttestationCreateResponse(
        attestation=result.attestation,
        proposal=result.proposal,
        receipt_ref=result.receipt_ref,
        admitted_proposal_version=ProposalVersionView(
            proposal_id=proposal_id,
            proposal_version_id=result.admitted_proposal_version_id,
            receipt_ref=result.admitted_proposal_receipt_ref,
        ),
        approved_is_not_execution_authorization=True,
        execution_allowed=False,
    )


class TimelineEntry(BaseModel):
    source_type: Literal["attestation", "review_event"]
    id: str
    kind: str
    created_at_utc: str
    attester: str
    reason: str
    detail: dict[str, Any] = Field(default_factory=dict)


class ProposalTimelineResponse(BaseModel):
    proposal_id: str
    is_archived: bool
    entries: list[TimelineEntry]
    non_claims: tuple[str, ...] = (
        "Review timeline is historical evidence only.",
        "Annotations and archive actions are not execution authorization.",
        "Not investment advice.",
    )
    execution_allowed: bool = False


class ReviewEventCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ReviewEventKind
    reason: str
    expected_proposal_version_id: str
    expected_proposal_receipt_ref: str
    text: str | None = None
    attestation_ref: str | None = None
    compare_with: str | None = None
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("reason", "expected_proposal_version_id", "expected_proposal_receipt_ref")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("this field is required and must not be blank")
        return value


class ReviewEventCreateResponse(BaseModel):
    review_event: ReviewEvent
    receipt_ref: str
    admitted_proposal_version: ProposalVersionView
    execution_allowed: bool = False


@router.get("/proposals/{proposal_id}/timeline", response_model=ProposalTimelineResponse)
async def get_proposal_timeline(
    proposal_id: str, engine: EngineDependency
) -> ProposalTimelineResponse:
    """Read-only merged review timeline: attestations + review events, newest first.

    Thin adapter over the Review-System read model (review_read). Attestation stays the
    decision of record; review events are the interaction ledger."""
    timeline = read_proposal_timeline(engine, proposal_id)
    if timeline is None:
        raise HTTPException(status_code=404, detail=f"proposal not found: {proposal_id}")
    return ProposalTimelineResponse(
        proposal_id=timeline.proposal_id,
        is_archived=timeline.is_archived,
        entries=[
            TimelineEntry(
                source_type=entry.source_type,
                id=entry.id,
                kind=entry.kind,
                created_at_utc=entry.created_at_utc,
                attester=entry.attester,
                reason=entry.reason,
                detail=entry.detail,
            )
            for entry in timeline.entries
        ],
        execution_allowed=False,
    )


@router.post("/proposals/{proposal_id}/review-events", response_model=ReviewEventCreateResponse)
async def add_review_event(
    proposal_id: str,
    request: ReviewEventCreateRequest,
    http_request: Request,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    operator: WriteCapabilityDependency,
) -> ReviewEventCreateResponse:
    binding = _route_identity_mutation_binding(
        http_request,
        effect_kind="api_review_event_create",
        operator=operator,
    )
    source_refs = list(request.source_refs)
    mutation_context: dict[str, Any] | None = None

    if binding is not None:
        mutation_ref, mutation_context = binding
        if mutation_ref not in source_refs:
            source_refs.append(mutation_ref)

    try:
        from finharness.statecore.proposal_version import ProposalVersionExpectation

        expectation = ProposalVersionExpectation(
            proposal_id=proposal_id,
            proposal_version_id=request.expected_proposal_version_id.strip(),
            receipt_ref=request.expected_proposal_receipt_ref.strip(),
        )
        result = create_governed_review_event(
            proposal_id=proposal_id,
            kind=request.kind,
            attester=operator.authoritative_actor_id,
            reason=request.reason.strip(),
            expectation=expectation,
            text=request.text,
            attestation_ref=request.attestation_ref,
            compare_with=request.compare_with,
            source_refs=source_refs,
            mutation_context=mutation_context,
            engine=engine,
            receipt_root=receipt_root,
        )
    except ProposalVersionResolutionError as exc:
        status = 404 if exc.code == "proposal_not_found" else 409
        detail: dict[str, Any] = {"code": exc.code, "message": str(exc)}
        if exc.code in ("proposal_version_conflict", "stale_expected_version", "stale_expected_receipt"):  # noqa: E501
            detail["proposal_id"] = proposal_id
            detail["execution_allowed"] = False
        raise HTTPException(status_code=status, detail=detail) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"proposal not found: {proposal_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except StateCoreStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ReviewEventCreateResponse(
        review_event=result.review_event,
        receipt_ref=result.receipt_ref,
        admitted_proposal_version=ProposalVersionView(
            proposal_id=proposal_id,
            proposal_version_id=result.admitted_proposal_version_id,
            receipt_ref=result.admitted_proposal_receipt_ref,
        ),
        execution_allowed=False,
    )
