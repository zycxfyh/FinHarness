#!/usr/bin/env python3
"""Exercise the minimal personal-capital Agent loop on isolated synthetic state."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session

from finharness.capital_agent import (
    CapitalAgentStore,
    EffectAdmissionDenied,
    EffectRecoveryRequired,
)
from finharness.execution.adapters.simulated_broker import SimulatedBrokerAdapter
from finharness.execution.broker import clear_broker_registry, register_broker_adapter
from finharness.personal_finance import ingest_personal_finance_export
from finharness.project_paths import ROOT
from finharness.statecore.capital_world import resolve_capital_world
from finharness.statecore.execution_models import (
    BrokerConnection,
    ExecutionAccount,
    ExecutionEnvironment,
)
from finharness.statecore.models import ImportBatch
from finharness.statecore.store import init_state_core, write_records


def _write_fixture(path: Path, *, at: str, quantity: str, value: str, cost: str) -> None:
    template = (ROOT / "tests/fixtures/capital_review/admitted.csv.template").read_text(
        encoding="utf-8"
    )
    text = template.replace("{{AS_OF_UTC}}", at).replace("{{VALUED_AT_UTC}}", at)
    text = text.replace("9,9000,8100", f"{quantity},{value},{cost}")
    path.write_text(text, encoding="utf-8")


def _require(value: bool, detail: str) -> None:
    if not value:
        raise RuntimeError(detail)


def run_acceptance() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="finharness-capital-agent-") as tmp:
        root = Path(tmp)
        engine = init_state_core(root / "state.sqlite")
        receipts = root / "receipts"
        agent_root = root / "agent"
        source = root / "capital.csv"
        now = datetime.now(UTC)
        t1 = (now - timedelta(days=2)).isoformat()
        t2 = (now - timedelta(days=1)).isoformat()
        _write_fixture(source, at=t1, quantity="9", value="9000", cost="8100")
        first_import = ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)
        with Session(engine) as session:
            first_batch = session.get(ImportBatch, first_import.batch_id)
            if first_batch is None or not first_batch.stable_source_id:
                raise RuntimeError("first import has no stable source identity")
            stable_source_id = first_batch.stable_source_id
        before = resolve_capital_world(
            engine=engine,
            as_of_utc=t1,
            known_at_utc="2099-01-01T00:00:00+00:00",
            use_case="agent_context",
        )
        _require(before.trust.status == "admitted", "initial Capital World not admitted")

        write_records(
            [
                BrokerConnection(
                    broker_connection_id="broker:acceptance",
                    environment=ExecutionEnvironment.PAPER,
                    broker_name="Acceptance simulated broker",
                    adapter_kind="simulated",
                    network_enabled=False,
                ),
                ExecutionAccount(
                    execution_account_id="execution:acceptance",
                    broker_connection_id="broker:acceptance",
                    environment=ExecutionEnvironment.PAPER,
                    account_label="Acceptance paper account",
                    funded=False,
                ),
            ],
            engine=engine,
        )
        register_broker_adapter("broker:acceptance", SimulatedBrokerAdapter())
        store = CapitalAgentStore(agent_root)
        constitution = store.create_constitution(
            principal_id="principal:acceptance",
            goals=("Reduce single-position concentration",),
            liquidity_floor=Decimal("1000"),
            max_simulated_notional=Decimal("3000"),
        )
        mission = store.create_mission(
            principal_id="principal:acceptance",
            agent_id="agent:acceptance",
            objective="Reduce SPY concentration through a simulated sale",
            success_conditions=("SPY quantity moves from 9 to 7",),
            constitution_id=constitution.constitution_id,
            world=before,
        )
        belief = store.create_belief(
            mission_id=mission.mission_id,
            claim="SPY concentration is above the desired level",
            confidence=Decimal("0.9"),
            evidence_refs=(f"capital-world:{before.world_id}",),
            review_condition="Review after the simulated effect is reconciled",
        )
        mission, checkpoint = store.checkpoint_mission(
            mission.mission_id,
            world=before,
            belief_refs=(store.ref(type(belief), belief.belief_id),),
            note="World and belief frozen before effect creation",
        )
        delegation = store.create_delegation(
            constitution_id=constitution.constitution_id,
            principal_id=mission.principal_id,
            agent_id=mission.agent_id,
            max_notional=Decimal("2500"),
            max_uses=4,
            expires_at_utc=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        )
        intent = store.create_effect_intent(
            mission_id=mission.mission_id,
            delegation_id=delegation.delegation_id,
            idempotency_key="reduce-spy-by-two",
            execution_account_id="execution:acceptance",
            broker_connection_id="broker:acceptance",
            instrument_ref="instrument:SPY",
            symbol="SPY",
            side="sell",
            order_type="limit",
            quantity=Decimal("2"),
            reference_price=Decimal("1000"),
            rationale="Reduce concentration while preserving cash",
        )
        _require(
            store.create_effect_intent(
                mission_id=mission.mission_id,
                delegation_id=delegation.delegation_id,
                idempotency_key="reduce-spy-by-two",
                execution_account_id="execution:acceptance",
                broker_connection_id="broker:acceptance",
                instrument_ref="instrument:SPY",
                symbol="SPY",
                side="sell",
                order_type="limit",
                quantity=Decimal("2"),
                reference_price=Decimal("1000"),
                rationale="Reduce concentration while preserving cash",
            )
            == intent,
            "effect intent was not idempotent",
        )
        admission = store.admit_effect(intent.effect_intent_id, current_world=before)
        execution = store.execute_simulated_effect(
            engine=engine,
            receipt_root=receipts / "execution",
            effect_intent_id=intent.effect_intent_id,
            admission_id=admission.admission_id,
            current_world=before,
            position_quantity_before=Decimal("9"),
        )
        replay = store.execute_simulated_effect(
            engine=engine,
            receipt_root=receipts / "execution",
            effect_intent_id=intent.effect_intent_id,
            admission_id=admission.admission_id,
            current_world=before,
            position_quantity_before=Decimal("9"),
        )
        _require(execution == replay, "duplicate effect executed twice")

        _write_fixture(source, at=t2, quantity="7", value="7000", cost="6300")
        ingest_personal_finance_export(
            source,
            engine=engine,
            receipt_root=receipts,
            source_id=stable_source_id,
        )
        after = resolve_capital_world(
            engine=engine,
            as_of_utc=t2,
            known_at_utc="2099-01-01T00:00:00+00:00",
            use_case="agent_context",
        )
        _require(before.world_id != after.world_id, "world did not change after effect")
        consequence = store.record_consequence(
            mission_id=mission.mission_id,
            execution_id=execution.execution_id,
            world_before=before,
            world_after=after,
            expected_change={"SPY_quantity": "7"},
            observed_change={"SPY_quantity": "7"},
        )
        mission, final_checkpoint = store.checkpoint_mission(
            mission.mission_id,
            world=after,
            belief_refs=(store.ref(type(belief), belief.belief_id),),
            effect_refs=(store.ref(type(execution), execution.execution_id),),
            note="Effect reconciled against the updated Capital World",
        )
        closed = store.close_mission(mission.mission_id, reason="success condition met")

        stale_rejected = False
        stale_mission = store.create_mission(
            principal_id="principal:acceptance",
            agent_id="agent:acceptance",
            objective="Prove stale-world rejection",
            success_conditions=("Admission is rejected",),
            constitution_id=constitution.constitution_id,
            world=before,
        )
        stale_delegation = store.create_delegation(
            constitution_id=constitution.constitution_id,
            principal_id=stale_mission.principal_id,
            agent_id=stale_mission.agent_id,
            max_notional=Decimal("1000"),
            max_uses=1,
            expires_at_utc=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        )
        stale_intent = store.create_effect_intent(
            mission_id=stale_mission.mission_id,
            delegation_id=stale_delegation.delegation_id,
            idempotency_key="stale-world",
            execution_account_id="execution:acceptance",
            broker_connection_id="broker:acceptance",
            instrument_ref="instrument:SPY",
            symbol="SPY",
            side="sell",
            order_type="limit",
            quantity=Decimal("1"),
            reference_price=Decimal("1000"),
            rationale="This intent must become stale",
        )
        try:
            store.admit_effect(stale_intent.effect_intent_id, current_world=after)
        except EffectAdmissionDenied as exc:
            stale_rejected = "stale_world" in str(exc)
        _require(stale_rejected, "stale-world effect was admitted")

        revoked = store.create_delegation(
            constitution_id=constitution.constitution_id,
            principal_id="principal:acceptance",
            agent_id="agent:acceptance",
            max_notional=Decimal("1000"),
            max_uses=1,
            expires_at_utc=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        )
        store.revoke_delegation(revoked.delegation_id, reason="acceptance revoke proof")
        revoked_mission = store.create_mission(
            principal_id="principal:acceptance",
            agent_id="agent:acceptance",
            objective="Prove revoke enforcement",
            success_conditions=("Admission is rejected",),
            constitution_id=constitution.constitution_id,
            world=after,
        )
        revoked_intent = store.create_effect_intent(
            mission_id=revoked_mission.mission_id,
            delegation_id=revoked.delegation_id,
            idempotency_key="revoked",
            execution_account_id="execution:acceptance",
            broker_connection_id="broker:acceptance",
            instrument_ref="instrument:SPY",
            symbol="SPY",
            side="sell",
            order_type="limit",
            quantity=Decimal("1"),
            reference_price=Decimal("1000"),
            rationale="This delegation is revoked",
        )
        revoked_rejected = False
        try:
            store.admit_effect(revoked_intent.effect_intent_id, current_world=after)
        except EffectAdmissionDenied as exc:
            revoked_rejected = "delegation_not_active" in str(exc)
        _require(revoked_rejected, "revoked delegation admitted an effect")

        recovery_intent = store.create_effect_intent(
            mission_id=revoked_mission.mission_id,
            delegation_id=stale_delegation.delegation_id,
            idempotency_key="recovery",
            execution_account_id="missing-account",
            broker_connection_id="missing-broker",
            instrument_ref="instrument:SPY",
            symbol="SPY",
            side="sell",
            order_type="limit",
            quantity=Decimal("1"),
            reference_price=Decimal("1000"),
            rationale="Force a claimed effect requiring reconciliation",
        )
        recovery_admission = store.admit_effect(
            recovery_intent.effect_intent_id, current_world=after
        )
        recovery_closed = False
        try:
            store.execute_simulated_effect(
                engine=engine,
                receipt_root=receipts / "execution",
                effect_intent_id=recovery_intent.effect_intent_id,
                admission_id=recovery_admission.admission_id,
                current_world=after,
                position_quantity_before=Decimal("7"),
            )
        except EffectRecoveryRequired as exc:
            recovered = store.reconcile_claimed_execution(
                Path(exc.execution_ref).stem,
                outcome="failed",
                evidence_refs=("state-core:no-effect",),
                reason="No execution account existed",
            )
            recovery_closed = recovered.state == "failed"
        _require(recovery_closed, "claimed effect was not reconciled")

        restarted = CapitalAgentStore(agent_root)
        _require(
            restarted.read_mission(closed.mission_id).state == "closed", "restart lost mission"
        )
        clear_broker_registry()
        engine.dispose()
        return {
            "ok": True,
            "constitution_id": constitution.constitution_id,
            "mission_id": closed.mission_id,
            "initial_checkpoint_id": checkpoint.checkpoint_id,
            "final_checkpoint_id": final_checkpoint.checkpoint_id,
            "effect_intent_id": intent.effect_intent_id,
            "admission_id": admission.admission_id,
            "execution_id": execution.execution_id,
            "consequence_id": consequence.consequence_id,
            "stale_world_rejected": stale_rejected,
            "revoked_delegation_rejected": revoked_rejected,
            "claimed_effect_reconciled": recovery_closed,
            "live_external_effects": False,
        }


def main() -> int:
    print(json.dumps(run_acceptance(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
