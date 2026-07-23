from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect

from finharness.api.app import create_app
from finharness.capital_agent import (
    CapitalAgentConflictError,
    CapitalAgentStore,
    EffectAdmissionDenied,
    EffectRecoveryRequired,
)
from finharness.execution.adapters.simulated_broker import SimulatedBrokerAdapter
from finharness.execution.broker import (
    clear_broker_registry,
    register_broker_adapter,
)
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.capital_world import (
    CapitalWorld,
    CapitalWorldQuery,
    CapitalWorldTrust,
)
from finharness.statecore.execution_models import (
    BrokerConnection,
    ExecutionAccount,
    ExecutionEnvironment,
)
from finharness.statecore.models import Position
from finharness.statecore.receipt_io import ReceiptIntegrityError
from finharness.statecore.store import init_state_core, write_records
from tests.asgi_test_client import AsgiTestClient


def _world(
    label: str,
    *,
    blockers: tuple[str, ...] = (),
    quantity: Decimal = Decimal("9"),
    unit_price: Decimal = Decimal("100"),
) -> CapitalWorld:
    basis = (label * 64)[:64]
    position = Position(
        position_id=f"position_{label}",
        snapshot_id=f"snapshot_{label}",
        account_id="exec:test",
        instrument_id="instrument:SPY",
        symbol="SPY",
        quantity=quantity,
        market_value=quantity * unit_price,
        cost_basis=quantity * Decimal("90"),
        valuation_currency="USD",
        unit_price=unit_price,
        price_currency="USD",
        valued_at_utc="2026-07-24T00:00:00+00:00",
        price_source_ref="test:price",
        valuation_status="valued",
    )
    return CapitalWorld(
        world_id=f"world_{label}",
        basis_digest=basis,
        query=CapitalWorldQuery(
            as_of_utc="2026-07-24T00:00:00+00:00",
            known_at_utc="2026-07-24T00:00:00+00:00",
            base_currency="USD",
            use_case="agent_context",
        ),
        selected_sources=(),
        records=({"record_type": "Position", "payload": position.model_dump(mode="python")},),
        trust=CapitalWorldTrust(
            status="blocked" if blockers else "admitted",
            evidence_integrity="intact",
            completeness="blocked" if blockers else "complete",
            valuation_status="blocked" if blockers else "admitted",
            blockers=blockers,
        ),
        recovery_refs=(),
    )


class CapitalAgentStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = CapitalAgentStore(self.root / "agent")
        self.world = _world("a")
        self.constitution = self.store.create_constitution(
            principal_id="principal:test",
            goals=("Reduce concentration",),
            liquidity_floor=Decimal("5000"),
            max_simulated_notional=Decimal("5000"),
        )
        self.mission = self.store.create_mission(
            principal_id="principal:test",
            agent_id="agent:test",
            objective="Reduce SPY concentration with a simulated sale",
            success_conditions=("Simulated sale is reconciled",),
            constitution_id=self.constitution.constitution_id,
            world=self.world,
        )
        self.delegation = self.store.create_delegation(
            constitution_id=self.constitution.constitution_id,
            principal_id="principal:test",
            agent_id="agent:test",
            max_notional=Decimal("2000"),
            max_uses=5,
            expires_at_utc=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        )
        self.addCleanup(self.tmp.cleanup)

    def _intent(self, key: str = "sell-spy"):
        return self.store.create_effect_intent(
            mission_id=self.mission.mission_id,
            delegation_id=self.delegation.delegation_id,
            idempotency_key=key,
            execution_account_id="exec:test",
            broker_connection_id="broker:test",
            instrument_ref="instrument:SPY",
            symbol="SPY",
            side="sell",
            order_type="limit",
            quantity=Decimal("2"),
            reference_price=Decimal("100"),
            rationale="Reduce concentration",
        )

    def test_restart_reads_checkpoint_and_mission_transitions(self) -> None:
        belief = self.store.create_belief(
            mission_id=self.mission.mission_id,
            claim="SPY is above the desired concentration threshold",
            confidence=Decimal("0.8"),
            evidence_refs=("capital-world/world_a",),
            review_condition="Review after the simulated sale",
        )
        mission, checkpoint = self.store.checkpoint_mission(
            self.mission.mission_id,
            world=self.world,
            belief_refs=(self.store.ref(type(belief), belief.belief_id),),
            note="Ready for a simulated effect",
        )
        paused = self.store.pause_mission(mission.mission_id, reason="restart test")
        restarted = CapitalAgentStore(self.root / "agent")
        self.assertEqual(
            restarted.read_mission(paused.mission_id).checkpoint_ref,
            self.store.ref(type(checkpoint), checkpoint.checkpoint_id),
        )
        resumed = restarted.resume_mission(paused.mission_id, world=self.world)
        self.assertEqual(resumed.state, "active")
        closed = restarted.close_mission(resumed.mission_id, reason="completed")
        self.assertEqual(closed.state, "closed")

    def test_tampered_mission_artifact_fails_integrity(self) -> None:
        path = self.root / "agent" / "missions" / f"{self.mission.mission_id}.json"
        payload = path.read_text(encoding="utf-8").replace(
            "Reduce SPY concentration", "Silently changed objective"
        )
        path.write_text(payload, encoding="utf-8")
        with self.assertRaises(ReceiptIntegrityError):
            CapitalAgentStore(self.root / "agent").read_mission(self.mission.mission_id)

    def test_admitted_effect_rejects_changed_world_before_execution(self) -> None:
        intent = self._intent("stale-admission")
        admission = self.store.admit_effect(intent.effect_intent_id, current_world=self.world)
        engine = init_state_core(self.root / "stale-admission.sqlite")
        self.addCleanup(engine.dispose)
        with self.assertRaisesRegex(EffectAdmissionDenied, "admission_world_is_stale"):
            self.store.execute_simulated_effect(
                engine=engine,
                receipt_root=self.root / "stale-admission-receipts",
                effect_intent_id=intent.effect_intent_id,
                admission_id=admission.admission_id,
                current_world=_world("b"),
            )

    def test_effect_intent_is_idempotent_and_conflicts_on_changed_payload(self) -> None:
        first = self._intent()
        second = self._intent()
        self.assertEqual(first, second)
        with self.assertRaises(CapitalAgentConflictError):
            self.store.create_effect_intent(
                mission_id=self.mission.mission_id,
                delegation_id=self.delegation.delegation_id,
                idempotency_key="sell-spy",
                execution_account_id="exec:test",
                broker_connection_id="broker:test",
                instrument_ref="instrument:SPY",
                symbol="SPY",
                side="sell",
                order_type="limit",
                quantity=Decimal("3"),
                reference_price=Decimal("100"),
                rationale="Changed payload",
            )

    def test_admission_rejects_stale_world_and_revoked_delegation(self) -> None:
        intent = self._intent()
        with self.assertRaisesRegex(EffectAdmissionDenied, "stale_world"):
            self.store.admit_effect(intent.effect_intent_id, current_world=_world("b"))
        self.store.revoke_delegation(self.delegation.delegation_id, reason="stop")
        with self.assertRaisesRegex(EffectAdmissionDenied, "delegation_not_active"):
            self.store.admit_effect(intent.effect_intent_id, current_world=self.world)

    def test_simulated_effect_runs_once_and_records_consequence(self) -> None:
        engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(engine.dispose)
        self.addCleanup(clear_broker_registry)
        write_records(
            [
                BrokerConnection(
                    broker_connection_id="broker:test",
                    environment=ExecutionEnvironment.PAPER,
                    broker_name="Test simulated broker",
                    adapter_kind="simulated",
                    network_enabled=False,
                ),
                ExecutionAccount(
                    execution_account_id="exec:test",
                    broker_connection_id="broker:test",
                    environment=ExecutionEnvironment.PAPER,
                    account_label="Test paper account",
                    funded=False,
                ),
            ],
            engine=engine,
        )
        register_broker_adapter("broker:test", SimulatedBrokerAdapter())
        intent = self._intent()
        admission = self.store.admit_effect(intent.effect_intent_id, current_world=self.world)
        execution = self.store.execute_simulated_effect(
            engine=engine,
            receipt_root=self.root / "execution-receipts",
            effect_intent_id=intent.effect_intent_id,
            admission_id=admission.admission_id,
            current_world=self.world,
        )
        replay = self.store.execute_simulated_effect(
            engine=engine,
            receipt_root=self.root / "execution-receipts",
            effect_intent_id=intent.effect_intent_id,
            admission_id=admission.admission_id,
            current_world=self.world,
        )
        self.assertEqual(execution, replay)
        self.assertEqual(execution.state, "completed")
        consequence = self.store.record_consequence(
            mission_id=self.mission.mission_id,
            execution_id=execution.execution_id,
            world_before=self.world,
            world_after=_world("b"),
            expected_change={"SPY_quantity": "7"},
            observed_change={"SPY_quantity": "7"},
        )
        replayed_consequence = self.store.record_consequence(
            mission_id=self.mission.mission_id,
            execution_id=execution.execution_id,
            world_before=self.world,
            world_after=_world("b"),
            expected_change={"SPY_quantity": "7"},
            observed_change={"SPY_quantity": "7"},
        )
        self.assertEqual(consequence, replayed_consequence)
        self.assertEqual(consequence.discrepancies, ())

    def test_ambiguous_execution_requires_explicit_reconciliation(self) -> None:
        intent = self.store.create_effect_intent(
            mission_id=self.mission.mission_id,
            delegation_id=self.delegation.delegation_id,
            idempotency_key="missing-account",
            execution_account_id="missing",
            broker_connection_id="missing",
            instrument_ref="instrument:SPY",
            symbol="SPY",
            side="sell",
            order_type="limit",
            quantity=Decimal("1"),
            reference_price=Decimal("100"),
            rationale="Force a recoverable failed attempt",
        )
        admission = self.store.admit_effect(intent.effect_intent_id, current_world=self.world)
        engine = init_state_core(self.root / "failed.sqlite")
        self.addCleanup(engine.dispose)
        with self.assertRaises(EffectRecoveryRequired) as caught:
            self.store.execute_simulated_effect(
                engine=engine,
                receipt_root=self.root / "failed-receipts",
                effect_intent_id=intent.effect_intent_id,
                admission_id=admission.admission_id,
                current_world=self.world,
            )
        execution_id = Path(caught.exception.execution_ref).stem
        recovered = self.store.reconcile_claimed_execution(
            execution_id,
            outcome="failed",
            evidence_refs=("state-core:no-effect",),
            reason="No execution account existed",
        )
        self.assertEqual(recovered.state, "failed")


class RetiredLegacySurfaceTest(unittest.TestCase):
    def test_fresh_schema_does_not_create_retired_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            engine = init_state_core(Path(tmp) / "state.sqlite")
            tables = set(inspect(engine).get_table_names())
            engine.dispose()
        retired = {
            "action_intents",
            "action_intent_authority_bindings",
            "action_intent_simulation_reports",
            "trade_plan_candidates",
            "capital_objective_fits",
            "trade_plan_review_gates",
            "paper_order_ticket_candidates",
            "paper_execution_receipts",
            "paper_accounts",
            "paper_positions",
        }
        self.assertFalse(tables & retired)

    def test_openapi_does_not_expose_retired_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = init_state_core(root / "state.sqlite")
            app = create_app(
                state_core_engine=engine,
                receipt_root=str(root / "receipts"),
                local_operator_context=LocalOperatorContext("retired-surface-test"),
            )
            client = AsgiTestClient(app)
            try:
                paths = set(client.get("/openapi.json").json()["paths"])
            finally:
                client.close()
                engine.dispose()
        retired_prefixes = (
            "/action-intents",
            "/trade-plan-candidates",
            "/capital-objective-fits",
            "/paper-order-ticket-candidates",
            "/paper-execution-receipts",
            "/paper-accounts",
        )
        self.assertFalse([path for path in paths if path.startswith(retired_prefixes)])


if __name__ == "__main__":
    unittest.main()
