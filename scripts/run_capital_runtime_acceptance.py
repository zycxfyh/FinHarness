#!/usr/bin/env python3
"""Prove Mission Effect -> Rust Job/Attempt -> Python Worker -> domain execution."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from finharness.capital_agent import CapitalAgentStore
from finharness.capital_runtime import CapitalRuntimePort
from finharness.identity import AgentRuntimeIdentity, OperatorContext, PrincipalIdentity
from finharness.personal_finance import ingest_personal_finance_export
from finharness.project_paths import ROOT
from finharness.statecore.capital_world import resolve_capital_world
from finharness.statecore.execution_models import (
    BrokerConnection,
    ExecutionAccount,
    ExecutionEnvironment,
)
from finharness.statecore.store import init_state_core, write_records


def _write_fixture(path: Path, *, at: str) -> None:
    template = (ROOT / "tests/fixtures/capital_review/admitted.csv.template").read_text(
        encoding="utf-8"
    )
    path.write_text(
        template.replace("{{AS_OF_UTC}}", at).replace("{{VALUED_AT_UTC}}", at),
        encoding="utf-8",
    )


def _require(value: bool, detail: str) -> None:
    if not value:
        raise RuntimeError(detail)


def run_acceptance() -> dict[str, object]:
    runtime_binary = ROOT / "target/debug/finharness-runtime"
    runner_binary = ROOT / "target/debug/finharness-task-runner"
    _require(runtime_binary.is_file(), "finharness-runtime is not built")
    _require(runner_binary.is_file(), "finharness-task-runner is not built")
    with tempfile.TemporaryDirectory(prefix="finharness-runtime-acceptance-") as tmp:
        root = Path(tmp)
        state_db = root / "state.sqlite"
        receipts = root / "receipts"
        engine = init_state_core(state_db)
        observed = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        source = root / "capital.csv"
        _write_fixture(source, at=observed)
        ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)
        world = resolve_capital_world(
            engine=engine,
            as_of_utc=observed,
            known_at_utc="2099-01-01T00:00:00+00:00",
            use_case="agent_context",
        )
        _require(world.trust.status == "admitted", "Capital World is not admitted")
        write_records(
            [
                BrokerConnection(
                    broker_connection_id="broker:runtime-acceptance",
                    environment=ExecutionEnvironment.PAPER,
                    broker_name="Runtime acceptance simulated broker",
                    adapter_kind="simulated",
                    network_enabled=False,
                ),
                ExecutionAccount(
                    execution_account_id="execution:runtime-acceptance",
                    broker_connection_id="broker:runtime-acceptance",
                    environment=ExecutionEnvironment.PAPER,
                    account_label="Runtime acceptance paper account",
                    funded=False,
                ),
            ],
            engine=engine,
        )
        store = CapitalAgentStore(root / "agent")
        constitution = store.create_constitution(
            principal_id="principal:runtime-acceptance",
            goals=("Prove recoverable capital execution",),
            liquidity_floor=Decimal("1000"),
            max_simulated_notional=Decimal("3000"),
        )
        mission = store.create_mission(
            principal_id=constitution.principal_id,
            agent_id="agent:runtime-acceptance",
            objective="Execute one system-derived simulated sale",
            success_conditions=("Runtime Job and Effect both complete once",),
            constitution_id=constitution.constitution_id,
            world=world,
        )
        delegation = store.create_delegation(
            constitution_id=constitution.constitution_id,
            principal_id=mission.principal_id,
            agent_id=mission.agent_id,
            max_notional=Decimal("2500"),
            max_uses=1,
            expires_at_utc=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        )
        intent = store.create_effect_intent(
            mission_id=mission.mission_id,
            delegation_id=delegation.delegation_id,
            idempotency_key="runtime-acceptance-sale",
            execution_account_id="execution:runtime-acceptance",
            broker_connection_id="broker:runtime-acceptance",
            instrument_ref="instrument:SPY",
            symbol="SPY",
            side="sell",
            order_type="limit",
            quantity=Decimal("2"),
            reference_price=Decimal("1"),
            rationale="Prove that Runtime execution uses the Capital World price",
        )
        admission = store.admit_effect(intent.effect_intent_id, current_world=world)
        operator = OperatorContext(
            principal=PrincipalIdentity(
                principal_id=mission.principal_id,
                provider_id="acceptance",
                principal_kind="human",
            ),
            agent_runtime=AgentRuntimeIdentity(
                agent_runtime_id=mission.agent_id,
                principal_id=mission.principal_id,
                provider_id="acceptance",
                agent_profile="capital-runtime-acceptance",
            ),
            authentication_method="acceptance",
            authenticated_at_utc=datetime.now(UTC).isoformat(),
        )
        port = CapitalRuntimePort(
            runtime_binary=runtime_binary,
            runner_binary=runner_binary,
            runtime_root=root / "runtime",
            working_root=root,
        )
        first_job, first_execution = port.submit_paper_effect(
            operator=operator,
            store=store,
            effect_intent_id=intent.effect_intent_id,
            admission_id=admission.admission_id,
            state_db_path=state_db,
            receipt_root=receipts / "execution",
            current_world=world,
        )
        replay_job, replay_execution = port.submit_paper_effect(
            operator=operator,
            store=store,
            effect_intent_id=intent.effect_intent_id,
            admission_id=admission.admission_id,
            state_db_path=state_db,
            receipt_root=receipts / "execution",
            current_world=world,
        )
        _require(first_job.status == "succeeded", "Runtime Job did not succeed")
        _require(first_job.job_id == replay_job.job_id, "Runtime idempotency created another Job")
        _require(
            first_execution.execution_id == replay_execution.execution_id,
            "Effect replay created another execution",
        )
        _require(
            first_execution.runtime_job_id == first_job.job_id,
            "Effect execution is not bound to Runtime Job",
        )
        _require(
            admission.verified_reference_price != intent.reference_price,
            "Acceptance did not prove World-owned price verification",
        )
        engine.dispose()
        return {
            "ok": True,
            "mission_id": mission.mission_id,
            "effect_intent_id": intent.effect_intent_id,
            "execution_id": first_execution.execution_id,
            "runtime_job_id": first_job.job_id,
            "runtime_attempt_id": first_job.attempt_id,
            "idempotent_replay": True,
            "verified_reference_price": str(admission.verified_reference_price),
            "caller_reference_price": str(intent.reference_price),
            "live_external_effects": False,
        }


def main() -> int:
    print(json.dumps(run_acceptance(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
