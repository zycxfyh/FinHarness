"""Authenticated Python port to the FinHarness recoverable Rust Runtime."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import sysconfig
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.capital_agent import (
    CapitalAgentNotFoundError,
    CapitalAgentStore,
    EffectExecutionRecord,
)
from finharness.identity import OperatorContext
from finharness.statecore.capital_world import CapitalWorld
from finharness.statecore.receipt_io import (
    canonical_json_sha256,
    durable_atomic_write_json,
)


class CapitalRuntimeError(RuntimeError):
    """Raised when the local execution Runtime rejects or loses an operation."""


class CapitalRuntimeRecoveryRequired(CapitalRuntimeError):
    def __init__(self, job_id: str, detail: str) -> None:
        self.job_id = job_id
        super().__init__(f"{detail}; reconcile Runtime Job {job_id}")


class RuntimeObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow", populate_by_name=True)

    job_id: str = Field(alias="jobId")
    status: str
    attempt_id: str | None = Field(default=None, alias="attemptId")
    exit_code: int | None = Field(default=None, alias="exitCode")
    stdout_tail: str = Field(default="", alias="stdoutTail")
    stderr_tail: str = Field(default="", alias="stderrTail")
    artifacts_available: bool = Field(default=False, alias="artifactsAvailable")
    error_summary: str | None = Field(default=None, alias="errorSummary")


class PaperEffectWorkerRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["finharness.paper_effect_worker.v1"] = (
        "finharness.paper_effect_worker.v1"
    )
    agent_root: str
    state_db_path: str
    receipt_root: str
    effect_intent_id: str
    admission_id: str
    expected_world_id: str
    expected_world_basis_digest: str
    as_of_utc: str
    known_at_utc: str
    base_currency: str


class PaperEffectWorkerResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_version: Literal["finharness.paper_effect_worker_result.v1"] = Field(
        default="finharness.paper_effect_worker_result.v1", alias="schemaVersion"
    )
    domain_outcome: Literal["completed", "recovery_required"] = Field(alias="domainOutcome")
    requires_reconciliation: bool = Field(alias="requiresReconciliation")
    execution_id: str = Field(alias="executionId")
    execution_state: str = Field(alias="executionState")
    execution_report_id: str | None = Field(default=None, alias="executionReportId")
    position_delta_id: str | None = Field(default=None, alias="positionDeltaId")
    reconciliation_id: str | None = Field(default=None, alias="reconciliationId")


@dataclass(frozen=True)
class CapitalRuntimePort:
    """Narrow local adapter; callers choose domain objects, never executables or environment."""

    runtime_binary: Path
    runner_binary: Path
    runtime_root: Path
    working_root: Path
    worker_python: Path = Path(sys.executable)
    global_limit: int = 2

    def build_paper_effect_request(
        self,
        *,
        operator: OperatorContext,
        store: CapitalAgentStore,
        effect_intent_id: str,
        admission_id: str,
        state_db_path: str | Path,
        receipt_root: str | Path,
        current_world: CapitalWorld,
    ) -> tuple[dict[str, Any], str, str]:
        runtime_identity = operator.agent_runtime
        if runtime_identity is None:
            raise CapitalRuntimeError("paper Effect execution requires an AgentRuntimeIdentity")
        intent = store.read_effect_intent(effect_intent_id)
        admission = store.read_effect_admission(admission_id)
        if admission.effect_intent_id != effect_intent_id:
            raise CapitalRuntimeError("admission does not bind the requested EffectIntent")
        operator.reject_identity_substitution(
            claimed_principal_id=intent.principal_id,
            claimed_agent_runtime_id=intent.agent_id,
        )
        if (
            current_world.world_id != admission.world_id
            or current_world.basis_digest != admission.world_basis_digest
        ):
            raise CapitalRuntimeError("Runtime request is not bound to the admitted Capital World")

        worker_request = PaperEffectWorkerRequest(
            agent_root=str(store.root.resolve()),
            state_db_path=str(Path(state_db_path).resolve()),
            receipt_root=str(Path(receipt_root).resolve()),
            effect_intent_id=effect_intent_id,
            admission_id=admission_id,
            expected_world_id=current_world.world_id,
            expected_world_basis_digest=current_world.basis_digest,
            as_of_utc=current_world.query.as_of_utc,
            known_at_utc=current_world.query.known_at_utc,
            base_currency=current_world.query.base_currency,
        )
        input_relative = self._persist_input(worker_request)
        payload: dict[str, Any] = {
            "schemaVersion": 1,
            "clientRequestId": f"effect.execute:{effect_intent_id}",
            "principalId": operator.principal.principal_id,
            "agentRuntimeId": runtime_identity.agent_runtime_id,
            "operationKind": "paper_effect.execute",
            "domainRef": f"effect:{effect_intent_id}",
            "scope": {
                "scopeId": effect_intent_id,
                "workingRoot": str(self.working_root.resolve()),
                "contextDigest": current_world.basis_digest,
                "resourceKey": f"broker-account:{intent.broker_connection_id}",
            },
            "inputPath": input_relative,
            "globalLimit": self.global_limit,
            "timeoutMs": 60_000,
            "stdoutLimitBytes": 256 * 1024,
            "stderrLimitBytes": 256 * 1024,
            "waitMs": 30_000,
            "stdoutTailBytes": 64 * 1024,
            "stderrTailBytes": 64 * 1024,
        }
        return payload, intent.principal_id, intent.agent_id

    def submit_paper_effect(
        self,
        *,
        operator: OperatorContext,
        store: CapitalAgentStore,
        effect_intent_id: str,
        admission_id: str,
        state_db_path: str | Path,
        receipt_root: str | Path,
        current_world: CapitalWorld,
    ) -> tuple[RuntimeObservation, EffectExecutionRecord]:
        payload, _principal_id, _agent_id = self.build_paper_effect_request(
            operator=operator,
            store=store,
            effect_intent_id=effect_intent_id,
            admission_id=admission_id,
            state_db_path=state_db_path,
            receipt_root=receipt_root,
            current_world=current_world,
        )
        observation = RuntimeObservation.model_validate(self._invoke("run", payload))
        execution_id = store.effect_execution_id(effect_intent_id)
        try:
            execution = store.read_effect_execution(execution_id)
        except CapitalAgentNotFoundError as exc:
            if observation.status in {"failed", "timed_out", "lost", "orphaned"}:
                raise CapitalRuntimeRecoveryRequired(
                    observation.job_id,
                    observation.error_summary or observation.stderr_tail or observation.status,
                ) from exc
            raise CapitalRuntimeError(
                "Runtime returned without an Effect execution record"
            ) from exc
        execution = store.bind_runtime_execution(
            execution.execution_id,
            runtime_job_id=observation.job_id,
            runtime_attempt_id=observation.attempt_id,
        )
        if observation.status != "succeeded":
            raise CapitalRuntimeRecoveryRequired(
                observation.job_id,
                observation.error_summary or observation.stderr_tail or observation.status,
            )
        result = PaperEffectWorkerResult.model_validate(_last_json_object(observation.stdout_tail))
        if result.execution_id != execution.execution_id or result.domain_outcome != "completed":
            raise CapitalRuntimeRecoveryRequired(
                observation.job_id,
                "Worker result does not prove the bound Effect completed",
            )
        return observation, execution

    def observe(self, job_id: str) -> RuntimeObservation:
        return RuntimeObservation.model_validate(
            self._invoke(
                "observe",
                {
                    "schemaVersion": 1,
                    "jobId": job_id,
                    "waitMs": 0,
                    "stdoutTailBytes": 64 * 1024,
                    "stderrTailBytes": 64 * 1024,
                },
            )
        )

    def _persist_input(self, request: PaperEffectWorkerRequest) -> str:
        root = self.working_root.resolve()
        input_root = root / ".finharness-runtime-inputs"
        payload = request.model_dump(mode="json")
        input_id = canonical_json_sha256(payload)
        target = input_root / f"paper-effect-{input_id}.json"
        durable_atomic_write_json(target, payload)
        return target.relative_to(root).as_posix()

    def _invoke(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        environment = os.environ.copy()
        environment.update(
            {
                "FINHARNESS_RUNTIME_ROOT": str(self.runtime_root.resolve()),
                "FINHARNESS_RUNTIME_RUNNER": str(self.runner_binary.resolve()),
                "FINHARNESS_RUNTIME_WORKER_PYTHON": str(self.worker_python.resolve()),
                "FINHARNESS_RUNTIME_WORKER_PYTHONPATH": os.pathsep.join(_runtime_python_paths()),
            }
        )
        completed = subprocess.run(  # noqa: S603
            [str(self.runtime_binary.resolve()), command],
            input=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            cwd=self.working_root.resolve(),
            env=environment,
            capture_output=True,
            text=True,
            timeout=75,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            try:
                error = _last_json_object(detail)
            except CapitalRuntimeError:
                raise CapitalRuntimeError(detail or "FinHarness Runtime failed") from None
            raise CapitalRuntimeError(
                f"{error.get('code', 'RUNTIME_ERROR')}: "
                f"{error.get('message', 'FinHarness Runtime failed')}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise CapitalRuntimeError("FinHarness Runtime returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise CapitalRuntimeError("FinHarness Runtime response is not an object")
        return payload


def _runtime_python_paths() -> tuple[str, ...]:
    candidates = [Path(__file__).resolve().parents[1]]
    runtime_paths = sysconfig.get_paths()
    candidates.extend(
        Path(value) for key in ("purelib", "platlib") if (value := runtime_paths.get(key))
    )
    return tuple(
        dict.fromkeys(str(candidate.resolve()) for candidate in candidates if candidate.exists())
    )


def _last_json_object(value: str) -> dict[str, Any]:
    for line in reversed(value.splitlines()):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise CapitalRuntimeError("no structured JSON result was found")


__all__ = [
    "CapitalRuntimeError",
    "CapitalRuntimePort",
    "CapitalRuntimeRecoveryRequired",
    "PaperEffectWorkerRequest",
    "PaperEffectWorkerResult",
    "RuntimeObservation",
]
