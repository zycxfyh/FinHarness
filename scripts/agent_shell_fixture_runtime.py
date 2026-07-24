"""Portable persisted Runtime fixture for Agent Shell browser and restart acceptance."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from finharness.capital_agent import CapitalAgentStore, EffectExecutionRecord
from finharness.capital_runtime import CapitalRuntimePort, RuntimeObservation
from finharness.execution.adapters.simulated_broker import SimulatedBrokerAdapter
from finharness.execution.broker import clear_broker_registry, register_broker_adapter
from finharness.identity import OperatorContext
from finharness.project_paths import ROOT
from finharness.statecore.capital_world import CapitalWorld
from finharness.statecore.execution_models import ExecutionEnvironment
from finharness.statecore.receipt_io import durable_atomic_write_json
from finharness.statecore.store import init_state_core

FixtureRuntimeMode = Literal["auto", "fixture", "systemd"]
ResolvedFixtureRuntimeMode = Literal["fixture", "systemd"]


def systemd_runtime_available() -> bool:
    """Return whether this process can use the root-owned systemd Runtime path."""

    return os.geteuid() == 0 and Path("/run/systemd/system").is_dir()


def resolve_fixture_runtime_mode(mode: FixtureRuntimeMode) -> ResolvedFixtureRuntimeMode:
    if mode == "fixture":
        return "fixture"
    if mode == "systemd":
        if not systemd_runtime_available():
            raise RuntimeError("systemd fixture Runtime requested but unavailable")
        return "systemd"
    return "systemd" if systemd_runtime_available() else "fixture"


@dataclass(frozen=True)
class PersistedFixtureRuntimePort:
    """Run the real simulated Execution Kernel and persist a Runtime observation."""

    root: Path

    @property
    def observation_root(self) -> Path:
        return self.root / "observations"

    def _observation_path(self, job_id: str) -> Path:
        return self.observation_root / f"{job_id}.json"

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
        engine = init_state_core(state_db_path)
        try:
            intent = store.read_effect_intent(effect_intent_id)
            operator.reject_identity_substitution(
                claimed_principal_id=intent.principal_id,
                claimed_agent_runtime_id=intent.agent_id,
            )
            register_broker_adapter(
                intent.broker_connection_id,
                SimulatedBrokerAdapter(environment=ExecutionEnvironment.PAPER),
            )
            execution = store.execute_simulated_effect(
                engine=engine,
                receipt_root=receipt_root,
                effect_intent_id=effect_intent_id,
                admission_id=admission_id,
                current_world=current_world,
            )
            suffix = effect_intent_id[-24:]
            job_id = f"job-fixture-{suffix}"
            attempt_id = f"attempt-fixture-{suffix}"
            execution = store.bind_runtime_execution(
                execution.execution_id,
                runtime_job_id=job_id,
                runtime_attempt_id=attempt_id,
            )
            observation = RuntimeObservation(
                job_id=job_id,
                status="succeeded",
                attempt_id=attempt_id,
                exit_code=0,
                stdout_tail=json.dumps(
                    {
                        "schemaVersion": "finharness.fixture_runtime_observation.v1",
                        "runtimeMode": "fixture",
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                stderr_tail="",
                artifacts_available=True,
            )
            durable_atomic_write_json(
                self._observation_path(job_id),
                observation.model_dump(mode="json", by_alias=True),
            )
            return observation, execution
        finally:
            clear_broker_registry()
            engine.dispose()

    def observe(self, job_id: str) -> RuntimeObservation:
        try:
            payload = json.loads(self._observation_path(job_id).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"fixture Runtime observation is unavailable: {job_id}") from exc
        return RuntimeObservation.model_validate(payload)


def build_fixture_runtime_port(
    root: Path,
    *,
    mode: FixtureRuntimeMode,
) -> tuple[ResolvedFixtureRuntimeMode, CapitalRuntimePort | PersistedFixtureRuntimePort]:
    resolved = resolve_fixture_runtime_mode(mode)
    if resolved == "fixture":
        return resolved, PersistedFixtureRuntimePort(root / "fixture-runtime")
    working_root = root / "runtime-work"
    working_root.mkdir(parents=True, exist_ok=True)
    return resolved, CapitalRuntimePort(
        runtime_binary=ROOT / "target/debug/finharness-runtime",
        runner_binary=ROOT / "target/debug/finharness-task-runner",
        runtime_root=root / "runtime",
        working_root=working_root,
    )
