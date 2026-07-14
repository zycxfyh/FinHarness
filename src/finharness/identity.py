"""Authenticated actor identities and provider-neutral operator context."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import uuid4

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator

from finharness.statecore.receipt_io import (
    durable_atomic_write_json,
    durable_compare_and_swap_json,
    durable_create_json_exclusive,
    resolve_under,
)

IDEMPOTENCY_HEADER = "Idempotency-Key"
IDENTITY_RECEIPT_HEADER = "X-FinHarness-Identity-Receipt"
IDEMPOTENT_REPLAY_HEADER = "X-FinHarness-Idempotent-Replay"
IDEMPOTENCY_SEMANTIC_HEADERS = ("content-type", "if-match")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


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
    cached = getattr(request.state, "operator_context", None)
    if isinstance(cached, OperatorContext):
        return cached
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


class IdentityMutationError(RuntimeError):
    """Raised when a mutation identity receipt is invalid or cannot be reconciled."""


@dataclass(frozen=True)
class IdentityMutationClaim:
    """Result of the durable before-mutation claim."""

    disposition: Literal["execute", "ambiguous", "replay", "conflict"]
    receipt_id: str
    receipt_path: Path
    payload: dict[str, Any]


def request_body_sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _canonical_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _with_content_hash(payload: dict[str, Any]) -> dict[str, Any]:
    bound = dict(payload)
    bound["content_sha256"] = _canonical_sha256(payload)
    return bound


def _require_valid_content_hash(payload: dict[str, Any]) -> None:
    claimed = payload.get("content_sha256")
    unhashed = {key: value for key, value in payload.items() if key != "content_sha256"}
    if not isinstance(claimed, str) or claimed != _canonical_sha256(unhashed):
        raise IdentityMutationError("mutation identity receipt content hash mismatch")


def _load_identity_mutation_receipt(path: Path) -> dict[str, Any]:
    """Read and integrity-check one mutation receipt."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityMutationError(f"existing mutation receipt is unreadable: {path}") from exc
    _require_valid_content_hash(payload)
    return payload


def load_identity_mutation_receipt(
    receipt_path: str | Path,
) -> dict[str, Any]:
    """Load an integrity-checked mutation receipt for typed reconciliation."""

    return _load_identity_mutation_receipt(Path(receipt_path))


def _transition_identity_mutation(
    path: Path,
    *,
    expected_payload: dict[str, Any],
    next_payload: dict[str, Any],
) -> None:
    """Apply exactly one terminal transition from the expected pending version."""

    expected_hash = expected_payload.get("content_sha256")
    if expected_payload.get("state") != "pending" or not isinstance(expected_hash, str):
        raise IdentityMutationError(
            "terminal transition requires an integrity-bound pending receipt"
        )
    if not durable_compare_and_swap_json(
        path,
        expected_content_sha256=expected_hash,
        expected_state="pending",
        payload=next_payload,
    ):
        raise IdentityMutationError("mutation receipt changed before terminal transition")


def _mutation_receipt_id(
    *, context: OperatorContext, method: str, path: str, idempotency_key: str
) -> str:
    agent_id = context.agent_runtime.agent_runtime_id if context.agent_runtime else ""
    canonical = "\n".join(
        [context.principal.principal_id, agent_id, method.upper(), path, idempotency_key]
    )
    return f"identity_mutation_{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"


def begin_identity_mutation(
    root: Path,
    *,
    context: OperatorContext,
    method: str,
    path: str,
    request_target: str,
    semantic_headers: dict[str, str],
    trace_id: str,
    idempotency_key: str,
    body_sha256: str,
) -> IdentityMutationClaim:
    """Durably claim a keyed mutation before its domain effect is invoked."""

    if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
        raise IdentityMutationError(
            "Idempotency-Key must be 8-128 characters from A-Z, a-z, 0-9, . _ : -"
        )
    receipt_id = _mutation_receipt_id(
        context=context,
        method=method,
        path=path,
        idempotency_key=idempotency_key,
    )
    target = resolve_under(root, f"{receipt_id}.json")
    normalized_headers = {
        name.lower(): value.strip()
        for name, value in semantic_headers.items()
        if name.lower() in IDEMPOTENCY_SEMANTIC_HEADERS
    }
    request_binding = {
        "method": method.upper(),
        "path": path,
        "target": request_target,
        "semantic_headers": dict(sorted(normalized_headers.items())),
        "body_sha256": body_sha256,
        "idempotency_key_sha256": hashlib.sha256(idempotency_key.encode()).hexdigest(),
    }
    pending = _with_content_hash(
        {
            "schema": "finharness.api_mutation_identity_receipt.v1",
            "receipt_id": receipt_id,
            "state": "pending",
            "created_at_utc": datetime.now(UTC).isoformat(),
            "request": request_binding | {"trace_ids": [trace_id]},
            "actor": context.receipt_binding(),
            "durability": "power_loss_durable",
            "execution_allowed": False,
            "non_claims": [
                "Authentication identity is not capital authority.",
                "Pending means the mutation outcome may be ambiguous; automatic retry is denied.",
                "This receipt does not authorize execution.",
            ],
        }
    )
    if durable_create_json_exclusive(target, pending):
        return IdentityMutationClaim("execute", receipt_id, target, pending)
    existing = _load_identity_mutation_receipt(target)
    existing_request = existing.get("request", {})
    same_request = all(existing_request.get(key) == value for key, value in request_binding.items())
    if not same_request:
        return IdentityMutationClaim("conflict", receipt_id, target, existing)
    state = existing.get("state")
    if state == "pending":
        return IdentityMutationClaim("ambiguous", receipt_id, target, existing)
    if state in {"committed", "rejected", "reconciled_applied"}:
        return IdentityMutationClaim("replay", receipt_id, target, existing)
    raise IdentityMutationError(f"unsupported mutation receipt state: {state!r}")


def complete_identity_mutation(
    claim: IdentityMutationClaim,
    *,
    trace_id: str,
    status_code: int,
    response_body: bytes,
    content_type: str | None,
) -> dict[str, Any]:
    """Persist the after-mutation response and close the ambiguous interval."""

    if claim.disposition != "execute" or claim.payload.get("state") != "pending":
        raise IdentityMutationError("only a newly claimed pending mutation can complete")
    request_payload = dict(claim.payload["request"])
    trace_ids = list(request_payload.get("trace_ids", []))
    if trace_id not in trace_ids:
        trace_ids.append(trace_id)
    request_payload["trace_ids"] = trace_ids
    completed = _with_content_hash(
        {
            **{key: value for key, value in claim.payload.items() if key != "content_sha256"},
            "state": "committed" if status_code < 400 else "rejected",
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "previous_content_sha256": claim.payload["content_sha256"],
            "request": request_payload,
            "response": {
                "status_code": status_code,
                "content_type": content_type,
                "body_base64": base64.b64encode(response_body).decode(),
                "body_sha256": hashlib.sha256(response_body).hexdigest(),
            },
        }
    )
    _transition_identity_mutation(
        claim.receipt_path,
        expected_payload=claim.payload,
        next_payload=completed,
    )
    return completed


def record_verified_identity_mutation_reconciliation(
    receipt_path: str | Path,
    *,
    expected_payload: dict[str, Any],
    reconciled_by: str,
    reason: str,
    resolver_id: str,
    evidence_refs: list[str],
    domain_effect: dict[str, Any],
    status_code: int,
    response_body: bytes,
    content_type: str = "application/json",
) -> dict[str, Any]:
    """Record a response produced by a typed, domain-verifying resolver.

    This is the terminal receipt writer, not the operator-facing reconciliation
    interface. Callers must first verify the domain row and its canonical receipt.
    """

    path = Path(receipt_path)
    _require_valid_content_hash(expected_payload)
    if expected_payload.get("state") != "pending":
        raise IdentityMutationError("only a pending mutation can be reconciled")
    if not reconciled_by.strip() or not reason.strip():
        raise IdentityMutationError("reconciliation requires an operator and written reason")
    if not resolver_id.strip():
        raise IdentityMutationError("reconciliation requires a typed resolver id")
    if not 200 <= status_code < 300:
        raise IdentityMutationError(
            "applied reconciliation requires a successful canonical response"
        )
    if len(response_body) > 1_048_576:
        raise IdentityMutationError("canonical reconciliation response exceeds the supported size")
    if not content_type.lower().startswith("application/json"):
        raise IdentityMutationError("canonical reconciliation response must be JSON")

    cleaned_evidence = list(
        dict.fromkeys(ref.strip() for ref in evidence_refs if isinstance(ref, str) and ref.strip())
    )
    if not cleaned_evidence:
        raise IdentityMutationError("reconciliation requires verified domain evidence refs")
    if not isinstance(domain_effect.get("kind"), str) or not isinstance(
        domain_effect.get("canonical_resource"), str
    ):
        raise IdentityMutationError("reconciliation domain effect is incomplete")

    reconciled = _with_content_hash(
        {
            **{key: value for key, value in expected_payload.items() if key != "content_sha256"},
            "state": "reconciled_applied",
            "completed_at_utc": datetime.now(UTC).isoformat(),
            "previous_content_sha256": expected_payload["content_sha256"],
            "response": {
                "status_code": status_code,
                "content_type": content_type,
                "body_base64": base64.b64encode(response_body).decode(),
                "body_sha256": hashlib.sha256(response_body).hexdigest(),
            },
            "reconciliation": {
                "resolver_id": resolver_id.strip(),
                "response_source": "canonical_route_reconstruction",
                "reconciled_by": reconciled_by.strip(),
                "reason": reason.strip(),
                "evidence_refs": cleaned_evidence,
                "domain_effect": domain_effect,
            },
        }
    )
    _transition_identity_mutation(
        path,
        expected_payload=expected_payload,
        next_payload=reconciled,
    )
    return reconciled


def replay_identity_mutation(payload: dict[str, Any]) -> tuple[int, bytes, str | None]:
    """Return the response bound by a completed/reconciled mutation receipt."""

    _require_valid_content_hash(payload)
    response = payload.get("response")
    if not isinstance(response, dict):
        raise IdentityMutationError("completed mutation receipt has no response binding")
    try:
        body = base64.b64decode(response["body_base64"], validate=True)
        status_code = int(response["status_code"])
    except (KeyError, TypeError, ValueError) as exc:
        raise IdentityMutationError("mutation response binding is invalid") from exc
    if hashlib.sha256(body).hexdigest() != response.get("body_sha256"):
        raise IdentityMutationError("mutation response body hash mismatch")
    content_type = response.get("content_type")
    return status_code, body, content_type if isinstance(content_type, str) else None


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

    receipt_id = f"identity_receipt_{uuid4().hex}"
    payload = {
        "schema": "finharness.authenticated_actor_receipt.v1",
        "receipt_id": receipt_id,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "request": {"method": method, "path": path, "trace_id": trace_id},
        "response_status_code": status_code,
        "actor": context.receipt_binding(),
        "durability": "power_loss_durable",
        "non_claims": [
            "Authentication identity is not capital authority.",
            "This receipt does not authorize execution.",
        ],
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["content_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    target = resolve_under(root, f"{receipt_id}.json")
    durable_atomic_write_json(target, payload)
    return target
