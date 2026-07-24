"""Authenticated Agent Shell routes over Mission, Capital World, and Runtime."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import Engine
from sqlmodel import Session
from starlette.routing import compile_path

from finharness.agent_shell import (
    AgentBootstrap,
    AgentShellConflictError,
    AgentShellError,
    AgentShellMutationRecoveryRequired,
    AgentShellService,
    AgentShellUnavailableError,
    AgentShellWorldChangedError,
    MissionBundle,
    MissionConversationReply,
    MissionMessageRequest,
    MissionWorldDrift,
    PaperEffectRequest,
    PaperEffectResult,
    StartMissionRequest,
    WorldRecoveryRequest,
    WorldRecoveryResult,
    agent_shell_effect_receipt_path,
    agent_shell_world_recovery_receipt_path,
    complete_paper_effect_domain_receipt_for_recovery,
    complete_world_recovery_domain_receipt_for_recovery,
)
from finharness.api.dependencies import EngineDependency, ReceiptRootDependency
from finharness.api.keyed_mutation_capabilities import IdentityMutationResolverContract
from finharness.capital_agent import (
    BeliefArtifact,
    CapitalAgentConflictError,
    CapitalAgentNotFoundError,
    EffectAdmission,
    EffectAdmissionDenied,
    EffectIntent,
    EffectRecoveryRequired,
)
from finharness.capital_runtime import (
    CapitalRuntimeError,
    CapitalRuntimeRecoveryRequired,
)
from finharness.identity import (
    IdentityMutationClaim,
    IdentityMutationError,
    OperatorContext,
    identity_mutation_source_ref,
    load_identity_mutation_receipt,
    record_verified_identity_mutation_reconciliation,
    require_authenticated_operator,
)
from finharness.statecore.capital_world import resolve_capital_world
from finharness.statecore.execution_models import (
    ExecutionReport,
    PositionDelta,
    ReconciliationReport,
)
from finharness.statecore.receipt_io import (
    ReceiptIntegrityError,
    canonical_json_sha256,
)

router = APIRouter(prefix="/agent", tags=["agent-shell"])

_PAPER_EFFECT_CAPABILITY_ID = "finharness.api.agent-shell.paper-effect.keyed.v1"
_PAPER_EFFECT_RECONCILIATION_RESOLVER = "finharness.api.agent_shell.paper_effect.v1"
_PAPER_EFFECT_PATH_TEMPLATE = "/agent/missions/{mission_id}/paper-effects"
_WORLD_RECOVERY_CAPABILITY_ID = "finharness.api.agent-shell.world-recovery.keyed.v1"
_WORLD_RECOVERY_RECONCILIATION_RESOLVER = "finharness.api.agent_shell.world_recovery.v1"
_WORLD_RECOVERY_PATH_TEMPLATE = "/agent/missions/{mission_id}/world-recovery"

OperatorDependency = Annotated[
    OperatorContext,
    Depends(require_authenticated_operator),
]


def _service(request: Request) -> AgentShellService:
    service = getattr(request.app.state, "agent_shell_service", None)
    if not isinstance(service, AgentShellService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "agent_shell_unavailable",
                "message": "The local Agent Shell is not configured for this process.",
                "live_execution_allowed": False,
            },
        )
    return service


def _raise_domain_error(exc: Exception) -> NoReturn:
    if isinstance(exc, CapitalAgentNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "agent_artifact_not_found",
                "message": str(exc),
                "live_execution_allowed": False,
            },
        ) from exc
    if isinstance(exc, AgentShellWorldChangedError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "mission_world_changed",
                "message": str(exc),
                "drift": exc.drift.model_dump(mode="json"),
                "live_execution_allowed": False,
            },
        ) from exc
    if isinstance(exc, (AgentShellUnavailableError, CapitalRuntimeRecoveryRequired)):
        detail: dict[str, object] = {
            "code": "agent_runtime_recovery_required",
            "message": str(exc),
            "live_execution_allowed": False,
        }
        if isinstance(exc, CapitalRuntimeRecoveryRequired):
            detail["runtime_job_id"] = exc.job_id
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        ) from exc
    if isinstance(
        exc,
        (
            AgentShellConflictError,
            CapitalAgentConflictError,
            EffectAdmissionDenied,
            EffectRecoveryRequired,
            CapitalRuntimeError,
            ReceiptIntegrityError,
            ValueError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "agent_shell_conflict",
                "message": str(exc),
                "live_execution_allowed": False,
            },
        ) from exc
    if isinstance(exc, AgentShellError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "agent_shell_failure",
                "message": str(exc),
                "live_execution_allowed": False,
            },
        ) from exc
    raise exc


@router.get("/bootstrap", response_model=AgentBootstrap)
async def bootstrap_agent_shell(
    request: Request,
    engine: EngineDependency,
    operator: OperatorDependency,
) -> AgentBootstrap:
    try:
        return _service(request).bootstrap(operator=operator, engine=engine)
    except Exception as exc:  # reduced to typed local product failures.
        _raise_domain_error(exc)


@router.post(
    "/missions",
    response_model=MissionBundle,
    status_code=status.HTTP_201_CREATED,
)
async def start_agent_mission(
    payload: StartMissionRequest,
    request: Request,
    engine: EngineDependency,
    operator: OperatorDependency,
) -> MissionBundle:
    try:
        return _service(request).start_mission(
            payload,
            operator=operator,
            engine=engine,
        )
    except Exception as exc:
        _raise_domain_error(exc)


@router.get("/missions/{mission_id}", response_model=MissionBundle)
async def get_agent_mission(
    mission_id: str,
    request: Request,
    engine: EngineDependency,
    operator: OperatorDependency,
) -> MissionBundle:
    try:
        return _service(request).mission_bundle(
            mission_id,
            operator=operator,
            engine=engine,
        )
    except Exception as exc:
        _raise_domain_error(exc)


@router.get(
    "/missions/{mission_id}/world-drift",
    response_model=MissionWorldDrift,
)
async def get_agent_mission_world_drift(
    mission_id: str,
    request: Request,
    engine: EngineDependency,
    operator: OperatorDependency,
) -> MissionWorldDrift:
    try:
        return _service(request).world_drift(
            mission_id,
            operator=operator,
            engine=engine,
        )
    except Exception as exc:
        _raise_domain_error(exc)


@router.post(
    "/missions/{mission_id}/world-recovery",
    response_model=WorldRecoveryResult,
)
async def recover_agent_mission_world(
    mission_id: str,
    payload: WorldRecoveryRequest,
    request: Request,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    operator: OperatorDependency,
) -> WorldRecoveryResult:
    try:
        identity_claim = getattr(request.state, "identity_mutation_claim", None)
        if not isinstance(identity_claim, IdentityMutationClaim):
            raise IdentityMutationError(
                "World recovery route requires one executing identity mutation claim"
            )
        return _service(request).recover_world(
            mission_id,
            payload,
            operator=operator,
            engine=engine,
            identity_claim=identity_claim,
            domain_receipt_root=receipt_root,
        )
    except AgentShellMutationRecoveryRequired as exc:
        request.state.identity_mutation_leave_pending = True
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "agent_shell_mutation_recovery_required",
                "message": str(exc),
                "domain_receipt_ref": exc.domain_receipt_ref,
                "live_execution_allowed": False,
            },
        ) from exc
    except Exception as exc:
        _raise_domain_error(exc)


@router.post(
    "/missions/{mission_id}/messages",
    response_model=MissionConversationReply,
)
async def converse_with_agent_mission(
    mission_id: str,
    payload: MissionMessageRequest,
    request: Request,
    engine: EngineDependency,
    operator: OperatorDependency,
) -> MissionConversationReply:
    try:
        return _service(request).converse(
            mission_id,
            payload,
            operator=operator,
            engine=engine,
        )
    except Exception as exc:
        _raise_domain_error(exc)


@router.post(
    "/missions/{mission_id}/paper-effects",
    response_model=PaperEffectResult,
)
async def execute_agent_paper_effect(
    mission_id: str,
    payload: PaperEffectRequest,
    request: Request,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    operator: OperatorDependency,
) -> PaperEffectResult:
    try:
        identity_claim = getattr(request.state, "identity_mutation_claim", None)
        if not isinstance(identity_claim, IdentityMutationClaim):
            raise IdentityMutationError(
                "paper Effect route requires one executing identity mutation claim"
            )
        return _service(request).execute_paper_effect(
            mission_id,
            payload,
            operator=operator,
            engine=engine,
            identity_claim=identity_claim,
            domain_receipt_root=receipt_root,
        )
    except AgentShellMutationRecoveryRequired as exc:
        request.state.identity_mutation_leave_pending = True
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "agent_shell_mutation_recovery_required",
                "message": str(exc),
                "domain_receipt_ref": exc.domain_receipt_ref,
                "live_execution_allowed": False,
            },
        ) from exc
    except Exception as exc:
        _raise_domain_error(exc)


def _load_paper_effect_domain_receipt(
    receipt_root: Path,
    receipt_id: str,
) -> tuple[Path, dict[str, Any]]:
    path = agent_shell_effect_receipt_path(receipt_root, receipt_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityMutationError(
            "verified Agent Shell paper Effect receipt is missing or unreadable"
        ) from exc
    if not isinstance(payload, dict):
        raise IdentityMutationError("Agent Shell paper Effect receipt is not an object")
    content_sha = payload.get("content_sha256")
    expected_sha = canonical_json_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    if content_sha != expected_sha:
        raise IdentityMutationError("Agent Shell paper Effect receipt hash does not match")
    if payload.get("schema") != "finharness.agent_shell_paper_effect_receipt.v2":
        raise IdentityMutationError("unsupported Agent Shell paper Effect receipt")
    if payload.get("state") not in {"pending", "completed"}:
        raise IdentityMutationError("unsupported Agent Shell paper Effect receipt state")
    return path, payload


def _require_agent_shell_mutation_binding(
    receipt: dict[str, Any],
    *,
    mutation: dict[str, Any],
    receipt_id: str,
    request_binding: dict[str, Any],
    effect_kind: str,
) -> None:
    context = receipt.get("mutation_context")
    capability = mutation.get("route_capability")
    actor = mutation.get("actor")
    if not isinstance(context, dict) or not isinstance(capability, dict):
        raise IdentityMutationError("Agent Shell domain mutation binding is missing")
    expected = {
        "schema": "finharness.api_domain_mutation_binding.v2",
        "effect_kind": effect_kind,
        "identity_mutation_receipt_id": receipt_id,
        "identity_mutation_request_body_sha256": request_binding.get("body_sha256"),
        "identity_mutation_request_target": request_binding.get("target"),
        "identity_mutation_method": request_binding.get("method"),
        "identity_mutation_path": request_binding.get("path"),
        "identity_mutation_route_capability_id": capability.get("capability_id"),
        "identity_mutation_route_capability_sha256": capability.get("capability_sha256"),
        "identity_mutation_canonical_path_template": capability.get("canonical_path_template"),
        "identity_mutation_resolver_id": capability.get("resolver_id"),
        "authenticated_actor_receipt_ref": identity_mutation_source_ref(receipt_id),
        "authenticated_actor": actor,
        "execution_allowed": False,
    }
    for key, value in expected.items():
        if context.get(key) != value:
            raise IdentityMutationError(f"Agent Shell mutation binding does not match: {key}")


def _paper_effect_receipt_models(
    receipt: dict[str, Any],
) -> tuple[PaperEffectRequest, EffectIntent, EffectAdmission]:
    try:
        return (
            PaperEffectRequest.model_validate(receipt.get("request")),
            EffectIntent.model_validate(receipt.get("effect_intent")),
            EffectAdmission.model_validate(receipt.get("admission")),
        )
    except ValueError as exc:
        raise IdentityMutationError("paper Effect domain receipt payload is invalid") from exc


def _recover_pending_paper_effect_response(
    *,
    receipt_path: Path,
    receipt: dict[str, Any],
    mission_id: str,
    intent: EffectIntent,
    admission: EffectAdmission,
    agent_shell_service: AgentShellService | None,
) -> PaperEffectResult:
    if agent_shell_service is None or agent_shell_service.runtime_port is None:
        raise IdentityMutationError(
            "pending paper Effect recovery requires the configured Agent Shell service"
        )
    execution_id = receipt.get("effect_execution_id")
    if not isinstance(execution_id, str):
        raise IdentityMutationError("pending paper Effect has no execution identity")
    try:
        execution = agent_shell_service.agent_store.read_effect_execution(execution_id)
    except (CapitalAgentNotFoundError, ReceiptIntegrityError) as exc:
        raise IdentityMutationError(
            "pending paper Effect has no verified execution artifact"
        ) from exc
    if not execution.runtime_job_id:
        raise IdentityMutationError("pending paper Effect has no Runtime Job identity")
    observation = agent_shell_service.runtime_port.observe(execution.runtime_job_id)
    if (
        observation.status != "succeeded"
        or not observation.attempt_id
        or execution.runtime_attempt_id != observation.attempt_id
    ):
        raise IdentityMutationError("pending paper Effect Runtime is not succeeded")
    response = PaperEffectResult(
        mission_id=mission_id,
        effect_intent=intent,
        admission_id=admission.admission_id,
        verified_reference_price=admission.verified_reference_price,
        admitted_notional=admission.admitted_notional,
        runtime=observation,
        execution=execution,
        domain_receipt_ref=receipt_path.as_posix(),
    )
    try:
        complete_paper_effect_domain_receipt_for_recovery(
            receipt_path,
            pending=receipt,
            result=response,
        )
    except (OSError, ReceiptIntegrityError, AgentShellConflictError) as exc:
        raise IdentityMutationError(
            "paper Effect domain receipt still cannot be completed"
        ) from exc
    return response


def _paper_effect_response_from_receipt(
    *,
    receipt_path: Path,
    receipt: dict[str, Any],
    mission_id: str,
    intent: EffectIntent,
    admission: EffectAdmission,
    agent_shell_service: AgentShellService | None,
) -> PaperEffectResult:
    if receipt.get("state") == "pending":
        return _recover_pending_paper_effect_response(
            receipt_path=receipt_path,
            receipt=receipt,
            mission_id=mission_id,
            intent=intent,
            admission=admission,
            agent_shell_service=agent_shell_service,
        )
    try:
        return PaperEffectResult.model_validate(receipt.get("response"))
    except ValueError as exc:
        raise IdentityMutationError(
            "completed paper Effect receipt has an invalid response"
        ) from exc


def _require_paper_effect_request_and_actor(
    *,
    request: PaperEffectRequest,
    intent: EffectIntent,
    admission: EffectAdmission,
    mutation: dict[str, Any],
    mission_id: str,
) -> None:
    actor = mutation.get("actor")
    if not isinstance(actor, dict):
        raise IdentityMutationError("paper Effect mutation actor is missing")
    if intent.mission_id != mission_id:
        raise IdentityMutationError("paper Effect Mission differs from the route")
    if (
        intent.idempotency_key != request.request_id
        or intent.symbol != request.symbol
        or intent.side != request.side
        or intent.quantity != request.quantity
        or intent.rationale != request.rationale
    ):
        raise IdentityMutationError("paper Effect request differs from EffectIntent truth")
    if intent.principal_id != actor.get("principal_id") or intent.agent_id != actor.get(
        "agent_runtime_id"
    ):
        raise IdentityMutationError("paper Effect actor differs from EffectIntent truth")
    if admission.effect_intent_id != intent.effect_intent_id or admission.mission_id != mission_id:
        raise IdentityMutationError("paper Effect admission differs from intent truth")


def _require_paper_effect_execution_truth(
    *,
    response: PaperEffectResult,
    intent: EffectIntent,
    admission: EffectAdmission,
    engine: Engine,
) -> None:
    execution = response.execution
    if response.effect_intent != intent:
        raise IdentityMutationError("paper Effect response differs from receipt truth")
    if (
        response.admission_id != admission.admission_id
        or admission.verified_reference_price != response.verified_reference_price
        or admission.admitted_notional != response.admitted_notional
    ):
        raise IdentityMutationError("paper Effect admission differs from response truth")
    if (
        execution.state != "completed"
        or response.runtime.status != "succeeded"
        or not execution.runtime_job_id
        or execution.runtime_job_id != response.runtime.job_id
        or execution.runtime_attempt_id != response.runtime.attempt_id
        or not execution.execution_report_id
        or not execution.position_delta_id
        or not execution.reconciliation_id
    ):
        raise IdentityMutationError("paper Effect execution is not completely reconciled")
    with Session(engine) as session:
        report = session.get(ExecutionReport, execution.execution_report_id)
        delta = session.get(PositionDelta, execution.position_delta_id)
        reconciliation = session.get(ReconciliationReport, execution.reconciliation_id)
    if report is None or delta is None or reconciliation is None:
        raise IdentityMutationError("paper Effect execution rows are incomplete")
    if (
        delta.execution_report_id != report.execution_report_id
        or delta.execution_account_id != intent.execution_account_id
        or delta.symbol.strip().upper() != intent.symbol.strip().upper()
        or reconciliation.execution_account_id != intent.execution_account_id
        or reconciliation.reconciliation_status != "matched"
    ):
        raise IdentityMutationError("paper Effect execution rows do not reconcile")


def _verified_paper_effect_response(
    *,
    receipt_path: Path,
    receipt: dict[str, Any],
    mutation: dict[str, Any],
    request_binding: dict[str, Any],
    mission_id: str,
    engine: Engine,
    agent_shell_service: AgentShellService | None,
) -> PaperEffectResult:
    if request_binding.get("target") != request_binding.get("path"):
        raise IdentityMutationError(
            "paper Effect reconciliation does not accept query-bearing targets"
        )
    request, intent, admission = _paper_effect_receipt_models(receipt)
    _require_paper_effect_request_and_actor(
        request=request,
        intent=intent,
        admission=admission,
        mutation=mutation,
        mission_id=mission_id,
    )
    response = _paper_effect_response_from_receipt(
        receipt_path=receipt_path,
        receipt=receipt,
        mission_id=mission_id,
        intent=intent,
        admission=admission,
        agent_shell_service=agent_shell_service,
    )
    if response.mission_id != mission_id:
        raise IdentityMutationError("paper Effect response Mission differs from route")
    _require_paper_effect_execution_truth(
        response=response,
        intent=intent,
        admission=admission,
        engine=engine,
    )
    return response


def reconcile_agent_shell_paper_effect_identity_mutation(
    receipt_path: str | Path,
    *,
    engine: Engine,
    receipt_root: str | Path,
    reconciled_by: str,
    reason: str,
    agent_shell_service: AgentShellService | None = None,
) -> dict[str, Any]:
    mutation_path = Path(receipt_path)
    mutation = load_identity_mutation_receipt(mutation_path)
    if mutation.get("state") != "pending":
        raise IdentityMutationError("only a pending mutation can be reconciled")
    receipt_id = mutation.get("receipt_id")
    request_binding = mutation.get("request")
    capability = mutation.get("route_capability")
    if not isinstance(receipt_id, str) or not isinstance(request_binding, dict):
        raise IdentityMutationError("paper Effect identity mutation is incomplete")
    if (
        not isinstance(capability, dict)
        or capability.get("capability_id") != _PAPER_EFFECT_CAPABILITY_ID
        or capability.get("resolver_id") != _PAPER_EFFECT_RECONCILIATION_RESOLVER
    ):
        raise IdentityMutationError("mutation capability is not Agent Shell paper Effect")
    path = request_binding.get("path")
    method = request_binding.get("method")
    route_regex, _format, _convertors = compile_path(_PAPER_EFFECT_PATH_TEMPLATE)
    matched = route_regex.fullmatch(path) if isinstance(path, str) else None
    if method != "POST" or matched is None:
        raise IdentityMutationError("paper Effect mutation route does not match")
    mission_id = matched.groupdict().get("mission_id")
    if not mission_id:
        raise IdentityMutationError("paper Effect mutation has no Mission id")
    domain_path, domain_receipt = _load_paper_effect_domain_receipt(
        Path(receipt_root),
        receipt_id,
    )
    _require_agent_shell_mutation_binding(
        domain_receipt,
        mutation=mutation,
        receipt_id=receipt_id,
        request_binding=request_binding,
        effect_kind="api_agent_shell_paper_effect",
    )
    response = _verified_paper_effect_response(
        receipt_path=domain_path,
        receipt=domain_receipt,
        mutation=mutation,
        request_binding=request_binding,
        mission_id=mission_id,
        engine=engine,
        agent_shell_service=agent_shell_service,
    )
    response_body = json.dumps(
        response.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    execution = response.execution
    return record_verified_identity_mutation_reconciliation(
        mutation_path,
        expected_payload=mutation,
        reconciled_by=reconciled_by,
        reason=reason,
        resolver_id=_PAPER_EFFECT_RECONCILIATION_RESOLVER,
        evidence_refs=[
            identity_mutation_source_ref(receipt_id),
            domain_path.as_posix(),
            f"execution-report:{execution.execution_report_id}",
            f"position-delta:{execution.position_delta_id}",
            f"reconciliation:{execution.reconciliation_id}",
        ],
        domain_effect={
            "kind": "agent_shell_paper_effect",
            "mission_id": mission_id,
            "effect_intent_id": response.effect_intent.effect_intent_id,
            "execution_id": execution.execution_id,
            "runtime_job_id": execution.runtime_job_id,
            "domain_receipt_ref": domain_path.as_posix(),
            "canonical_resource": (
                f"/agent/missions/{mission_id}/paper-effects/"
                f"{response.effect_intent.effect_intent_id}"
            ),
            "execution_allowed": False,
        },
        status_code=200,
        response_body=response_body,
        content_type="application/json",
    )


def _load_world_recovery_domain_receipt(
    receipt_root: Path,
    receipt_id: str,
) -> tuple[Path, dict[str, Any]]:
    path = agent_shell_world_recovery_receipt_path(receipt_root, receipt_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IdentityMutationError(
            "verified Agent Shell World recovery receipt is missing or unreadable"
        ) from exc
    if not isinstance(payload, dict):
        raise IdentityMutationError("World recovery receipt is not an object")
    claimed = payload.get("content_sha256")
    expected = canonical_json_sha256(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    if claimed != expected:
        raise IdentityMutationError("World recovery receipt hash does not match")
    if payload.get("schema") != "finharness.agent_shell_world_recovery_receipt.v1":
        raise IdentityMutationError("unsupported World recovery receipt")
    if payload.get("state") not in {"pending", "completed"}:
        raise IdentityMutationError("unsupported World recovery receipt state")
    return path, payload


def _verified_world_recovery_artifacts(
    *,
    receipt_path: Path,
    receipt: dict[str, Any],
    mission_id: str,
    engine: Engine,
    agent_shell_service: AgentShellService | None,
) -> WorldRecoveryResult:
    if agent_shell_service is None:
        raise IdentityMutationError(
            "World recovery reconciliation requires the configured Agent Shell service"
        )
    record = receipt.get("record")
    if not isinstance(record, dict):
        raise IdentityMutationError("World recovery has no recovery record")
    if record.get("mission_id") != mission_id:
        raise IdentityMutationError("World recovery Mission differs from route")
    required_record_fields = (
        "checkpoint_id",
        "belief_id",
        "previous_mission_state",
        "previous_world_id",
        "previous_world_basis_digest",
        "target_world_id",
        "target_world_basis_digest",
        "recovery_id",
        "created_at_utc",
    )
    if any(not isinstance(record.get(field), str) for field in required_record_fields):
        raise IdentityMutationError("World recovery record is incomplete")
    try:
        target_world = MissionWorldDrift.model_validate(
            {
                "mission_id": mission_id,
                "drifted": False,
                "mission_world_id": record["target_world_id"],
                "mission_world_basis_digest": record["target_world_basis_digest"],
                "current_world": receipt.get("target_world"),
                "can_checkpoint_and_resume": False,
            }
        ).current_world
        request = WorldRecoveryRequest.model_validate(receipt.get("request"))
    except ValueError as exc:
        raise IdentityMutationError("World recovery payload is invalid") from exc
    current_world = resolve_capital_world(engine=engine, use_case="agent_context")
    if (
        current_world.trust.status != "admitted"
        or current_world.world_id != record["target_world_id"]
        or current_world.basis_digest != record["target_world_basis_digest"]
        or target_world.world_id != current_world.world_id
        or target_world.basis_digest != current_world.basis_digest
    ):
        raise IdentityMutationError("World recovery target is no longer the admitted Capital World")
    if receipt.get("state") == "pending":
        mission, checkpoint = agent_shell_service.apply_world_recovery_checkpoint(
            mission_id,
            world=current_world,
            belief_id=record["belief_id"],
            previous_mission_state=record["previous_mission_state"],
            previous_world_id=record["previous_world_id"],
            previous_world_basis_digest=record["previous_world_basis_digest"],
            note=request.note,
            checkpoint_id=record["checkpoint_id"],
            created_at_utc=record["created_at_utc"],
        )
    else:
        mission = agent_shell_service.agent_store.read_mission(mission_id)
        checkpoint = agent_shell_service.agent_store.read_checkpoint(record["checkpoint_id"])
    expected_checkpoint_ref = agent_shell_service.agent_store.ref(
        type(checkpoint), checkpoint.checkpoint_id
    )
    expected_belief_ref = agent_shell_service.agent_store.ref(BeliefArtifact, record["belief_id"])
    if (
        mission.state != "active"
        or mission.current_world_id != record["target_world_id"]
        or mission.current_world_basis_digest != record["target_world_basis_digest"]
        or checkpoint.world_id != mission.current_world_id
        or checkpoint.world_basis_digest != mission.current_world_basis_digest
        or checkpoint.belief_refs != (expected_belief_ref,)
        or mission.checkpoint_ref != expected_checkpoint_ref
    ):
        raise IdentityMutationError("World recovery artifacts do not match target World")
    return WorldRecoveryResult(
        recovery_id=record["recovery_id"],
        request_id=request.request_id,
        mission_id=mission_id,
        previous_world_id=record["previous_world_id"],
        previous_world_basis_digest=record["previous_world_basis_digest"],
        current_world=target_world,
        checkpoint=checkpoint,
        mission=mission,
        domain_receipt_ref=receipt_path.as_posix(),
        recovered_at_utc=record["created_at_utc"],
    )


def _world_recovery_response_from_receipt(
    *,
    receipt_path: Path,
    receipt: dict[str, Any],
    mission_id: str,
    engine: Engine,
    agent_shell_service: AgentShellService | None,
) -> WorldRecoveryResult:
    verified = _verified_world_recovery_artifacts(
        receipt_path=receipt_path,
        receipt=receipt,
        mission_id=mission_id,
        engine=engine,
        agent_shell_service=agent_shell_service,
    )
    if receipt.get("state") == "completed":
        try:
            completed = WorldRecoveryResult.model_validate(receipt.get("response"))
        except ValueError as exc:
            raise IdentityMutationError(
                "completed World recovery receipt has an invalid response"
            ) from exc
        if completed != verified:
            raise IdentityMutationError(
                "completed World recovery receipt differs from canonical artifacts"
            )
        return completed
    try:
        complete_world_recovery_domain_receipt_for_recovery(
            receipt_path,
            pending=receipt,
            result=verified,
        )
    except (OSError, ReceiptIntegrityError, AgentShellConflictError) as exc:
        raise IdentityMutationError(
            "World recovery domain receipt still cannot be completed"
        ) from exc
    return verified


def reconcile_agent_shell_world_recovery_identity_mutation(
    receipt_path: str | Path,
    *,
    engine: Engine,
    receipt_root: str | Path,
    reconciled_by: str,
    reason: str,
    agent_shell_service: AgentShellService | None = None,
) -> dict[str, Any]:
    mutation_path = Path(receipt_path)
    mutation = load_identity_mutation_receipt(mutation_path)
    if mutation.get("state") != "pending":
        raise IdentityMutationError("only a pending mutation can be reconciled")
    receipt_id = mutation.get("receipt_id")
    request_binding = mutation.get("request")
    capability = mutation.get("route_capability")
    if not isinstance(receipt_id, str) or not isinstance(request_binding, dict):
        raise IdentityMutationError("World recovery identity mutation is incomplete")
    if (
        not isinstance(capability, dict)
        or capability.get("capability_id") != _WORLD_RECOVERY_CAPABILITY_ID
        or capability.get("resolver_id") != _WORLD_RECOVERY_RECONCILIATION_RESOLVER
    ):
        raise IdentityMutationError("mutation capability is not World recovery")
    path = request_binding.get("path")
    route_regex, _format, _convertors = compile_path(_WORLD_RECOVERY_PATH_TEMPLATE)
    matched = route_regex.fullmatch(path) if isinstance(path, str) else None
    if request_binding.get("method") != "POST" or matched is None:
        raise IdentityMutationError("World recovery mutation route does not match")
    mission_id = matched.groupdict().get("mission_id")
    if not mission_id:
        raise IdentityMutationError("World recovery mutation has no Mission id")
    domain_path, domain_receipt = _load_world_recovery_domain_receipt(
        Path(receipt_root),
        receipt_id,
    )
    _require_agent_shell_mutation_binding(
        domain_receipt,
        mutation=mutation,
        receipt_id=receipt_id,
        request_binding=request_binding,
        effect_kind="api_agent_shell_world_recovery",
    )
    response = _world_recovery_response_from_receipt(
        receipt_path=domain_path,
        receipt=domain_receipt,
        mission_id=mission_id,
        engine=engine,
        agent_shell_service=agent_shell_service,
    )
    response_body = json.dumps(
        response.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return record_verified_identity_mutation_reconciliation(
        mutation_path,
        expected_payload=mutation,
        reconciled_by=reconciled_by,
        reason=reason,
        resolver_id=_WORLD_RECOVERY_RECONCILIATION_RESOLVER,
        evidence_refs=[
            identity_mutation_source_ref(receipt_id),
            domain_path.as_posix(),
            f"mission:{mission_id}",
            f"checkpoint:{response.checkpoint.checkpoint_id}",
        ],
        domain_effect={
            "kind": "agent_shell_world_recovery",
            "mission_id": mission_id,
            "checkpoint_id": response.checkpoint.checkpoint_id,
            "world_id": response.current_world.world_id,
            "domain_receipt_ref": domain_path.as_posix(),
            "canonical_resource": f"/agent/missions/{mission_id}",
            "execution_allowed": False,
        },
        status_code=200,
        response_body=response_body,
        content_type="application/json",
    )


def _dispatch_agent_shell_world_recovery(
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
    agent_shell_service: AgentShellService | None = None,
) -> dict[str, Any]:
    del mutation, receipt_id, request_binding
    if proposal_id is not None:
        raise IdentityMutationError("World recovery resolver cannot bind a Proposal id")
    return reconcile_agent_shell_world_recovery_identity_mutation(
        mutation_path,
        engine=engine,
        receipt_root=receipt_root,
        reconciled_by=reconciled_by,
        reason=reason,
        agent_shell_service=agent_shell_service,
    )


def _dispatch_agent_shell_paper_effect(
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
    agent_shell_service: AgentShellService | None = None,
) -> dict[str, Any]:
    del mutation, receipt_id, request_binding
    if proposal_id is not None:
        raise IdentityMutationError("paper Effect resolver cannot bind a Proposal id")
    return reconcile_agent_shell_paper_effect_identity_mutation(
        mutation_path,
        engine=engine,
        receipt_root=receipt_root,
        reconciled_by=reconciled_by,
        reason=reason,
        agent_shell_service=agent_shell_service,
    )


_AGENT_SHELL_IDENTITY_MUTATION_RECONCILIATION_CONTRACTS = (
    IdentityMutationResolverContract(
        capability_id=_WORLD_RECOVERY_CAPABILITY_ID,
        resolver_id=_WORLD_RECOVERY_RECONCILIATION_RESOLVER,
        method="POST",
        canonical_path_template=_WORLD_RECOVERY_PATH_TEMPLATE,
        handler=_dispatch_agent_shell_world_recovery,
        service_key="agent_shell_service",
    ),
    IdentityMutationResolverContract(
        capability_id=_PAPER_EFFECT_CAPABILITY_ID,
        resolver_id=_PAPER_EFFECT_RECONCILIATION_RESOLVER,
        method="POST",
        canonical_path_template=_PAPER_EFFECT_PATH_TEMPLATE,
        handler=_dispatch_agent_shell_paper_effect,
        service_key="agent_shell_service",
    ),
)


def agent_shell_identity_mutation_reconciliation_contracts() -> tuple[
    IdentityMutationResolverContract, ...
]:
    return _AGENT_SHELL_IDENTITY_MUTATION_RECONCILIATION_CONTRACTS
