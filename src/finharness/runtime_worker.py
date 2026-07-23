"""Pre-registered FinHarness Runtime workers.

This module is invoked by the Rust Runtime. It accepts domain references and a bounded input
artifact, never model-authored Python, shell, environment, credentials, or executable paths.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlmodel import Session

from finharness.capital_agent import CapitalAgentStore
from finharness.capital_runtime import PaperEffectWorkerRequest, PaperEffectWorkerResult
from finharness.execution.adapters.simulated_broker import SimulatedBrokerAdapter
from finharness.execution.broker import clear_broker_registry, register_broker_adapter
from finharness.statecore.capital_world import resolve_capital_world
from finharness.statecore.execution_models import (
    BrokerConnection,
    ExecutionEnvironment,
)
from finharness.statecore.store import init_state_core


class RuntimeWorkerError(RuntimeError):
    pass


def execute_paper_effect_worker(
    request: PaperEffectWorkerRequest,
    *,
    principal_id: str,
    agent_runtime_id: str,
) -> PaperEffectWorkerResult:
    engine = init_state_core(Path(request.state_db_path))
    try:
        store = CapitalAgentStore(request.agent_root)
        intent = store.read_effect_intent(request.effect_intent_id)
        if intent.principal_id != principal_id or intent.agent_id != agent_runtime_id:
            raise RuntimeWorkerError("authenticated Runtime identity does not bind EffectIntent")
        world = resolve_capital_world(
            engine=engine,
            as_of_utc=request.as_of_utc,
            known_at_utc=request.known_at_utc,
            base_currency=request.base_currency,
            use_case="agent_context",
        )
        if (
            world.world_id != request.expected_world_id
            or world.basis_digest != request.expected_world_basis_digest
        ):
            raise RuntimeWorkerError("Capital World changed before Worker execution")
        with Session(engine) as session:
            connection = session.get(BrokerConnection, intent.broker_connection_id)
        if connection is None or not connection.enabled:
            raise RuntimeWorkerError("broker connection is unavailable")
        if (
            connection.environment != ExecutionEnvironment.PAPER.value
            or connection.adapter_kind != "simulated"
            or connection.network_enabled
        ):
            raise RuntimeWorkerError("T13 only permits the offline simulated paper adapter")
        register_broker_adapter(
            connection.broker_connection_id,
            SimulatedBrokerAdapter(environment=ExecutionEnvironment.PAPER),
        )
        execution = store.execute_simulated_effect(
            engine=engine,
            receipt_root=request.receipt_root,
            effect_intent_id=request.effect_intent_id,
            admission_id=request.admission_id,
            current_world=world,
        )
        return PaperEffectWorkerResult(
            domain_outcome="completed",
            requires_reconciliation=False,
            execution_id=execution.execution_id,
            execution_state=execution.state,
            execution_report_id=execution.execution_report_id,
            position_delta_id=execution.position_delta_id,
            reconciliation_id=execution.reconciliation_id,
        )
    finally:
        clear_broker_registry()
        engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one registered FinHarness capital worker")
    parser.add_argument("--operation-kind", required=True)
    parser.add_argument("--domain-ref", required=True)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--agent-runtime-id", required=True)
    parser.add_argument("--input-path", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.operation_kind != "paper_effect.execute":
        raise RuntimeWorkerError("operation kind is not registered by this Worker")
    request = PaperEffectWorkerRequest.model_validate_json(
        Path(args.input_path).read_text(encoding="utf-8")
    )
    if args.domain_ref != f"effect:{request.effect_intent_id}":
        raise RuntimeWorkerError("domainRef does not bind the Worker input")
    result = execute_paper_effect_worker(
        request,
        principal_id=args.principal_id,
        agent_runtime_id=args.agent_runtime_id,
    )
    print(result.model_dump_json(by_alias=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
