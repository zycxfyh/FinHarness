from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session

from finharness.capital_agent import CapitalAgentStore
from finharness.capital_runtime import CapitalRuntimePort, PaperEffectWorkerRequest
from finharness.identity import AgentRuntimeIdentity, OperatorContext, PrincipalIdentity
from finharness.personal_finance import ingest_personal_finance_export
from finharness.project_paths import ROOT
from finharness.runtime_worker import execute_paper_effect_worker
from finharness.statecore.capital_world import resolve_capital_world
from finharness.statecore.execution_models import (
    BrokerConnection,
    ExecutionAccount,
    ExecutionEnvironment,
)
from finharness.statecore.models import ImportBatch
from finharness.statecore.store import init_state_core, write_records


def _write_fixture(path: Path, *, at: str) -> None:
    template = (ROOT / "tests/fixtures/capital_review/admitted.csv.template").read_text(
        encoding="utf-8"
    )
    text = template.replace("{{AS_OF_UTC}}", at).replace("{{VALUED_AT_UTC}}", at)
    path.write_text(text, encoding="utf-8")


class CapitalRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state_db = self.root / "state.sqlite"
        self.engine = init_state_core(self.state_db)
        self.addCleanup(self.engine.dispose)
        self.receipts = self.root / "receipts"
        source = self.root / "capital.csv"
        observed = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        _write_fixture(source, at=observed)
        imported = ingest_personal_finance_export(
            source,
            engine=self.engine,
            receipt_root=self.receipts,
        )
        with Session(self.engine) as session:
            batch = session.get(ImportBatch, imported.batch_id)
            self.assertIsNotNone(batch)
        self.world = resolve_capital_world(
            engine=self.engine,
            as_of_utc=observed,
            known_at_utc="2099-01-01T00:00:00+00:00",
            use_case="agent_context",
        )
        self.assertEqual(self.world.trust.status, "admitted")
        write_records(
            [
                BrokerConnection(
                    broker_connection_id="broker:runtime-test",
                    environment=ExecutionEnvironment.PAPER,
                    broker_name="Runtime simulated broker",
                    adapter_kind="simulated",
                    network_enabled=False,
                ),
                ExecutionAccount(
                    execution_account_id="execution:runtime-test",
                    broker_connection_id="broker:runtime-test",
                    environment=ExecutionEnvironment.PAPER,
                    account_label="Runtime paper account",
                    funded=False,
                ),
            ],
            engine=self.engine,
        )
        self.store = CapitalAgentStore(self.root / "agent")
        constitution = self.store.create_constitution(
            principal_id="principal:runtime-test",
            goals=("Exercise one recoverable paper Effect",),
            liquidity_floor=Decimal("1000"),
            max_simulated_notional=Decimal("3000"),
        )
        mission = self.store.create_mission(
            principal_id="principal:runtime-test",
            agent_id="agent:runtime-test",
            objective="Reduce SPY concentration",
            success_conditions=("Paper Effect is reconciled",),
            constitution_id=constitution.constitution_id,
            world=self.world,
        )
        delegation = self.store.create_delegation(
            constitution_id=constitution.constitution_id,
            principal_id=mission.principal_id,
            agent_id=mission.agent_id,
            max_notional=Decimal("2500"),
            max_uses=1,
            expires_at_utc=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        )
        self.intent = self.store.create_effect_intent(
            mission_id=mission.mission_id,
            delegation_id=delegation.delegation_id,
            idempotency_key="runtime-paper-effect",
            execution_account_id="execution:runtime-test",
            broker_connection_id="broker:runtime-test",
            instrument_ref="instrument:SPY",
            symbol="SPY",
            side="sell",
            order_type="limit",
            quantity=Decimal("2"),
            reference_price=Decimal("1"),
            rationale="The World, not the caller, owns the verified price",
        )
        self.admission = self.store.admit_effect(
            self.intent.effect_intent_id,
            current_world=self.world,
        )
        self.operator = OperatorContext(
            principal=PrincipalIdentity(
                principal_id=mission.principal_id,
                provider_id="test-provider",
                principal_kind="human",
            ),
            agent_runtime=AgentRuntimeIdentity(
                agent_runtime_id=mission.agent_id,
                principal_id=mission.principal_id,
                provider_id="test-provider",
                agent_profile="capital-runtime-test",
            ),
            authentication_method="test",
            authenticated_at_utc=datetime.now(UTC).isoformat(),
        )

    def _worker_request(self) -> PaperEffectWorkerRequest:
        return PaperEffectWorkerRequest(
            agent_root=str(self.store.root),
            state_db_path=str(self.state_db),
            receipt_root=str(self.receipts / "execution"),
            effect_intent_id=self.intent.effect_intent_id,
            admission_id=self.admission.admission_id,
            expected_world_id=self.world.world_id,
            expected_world_basis_digest=self.world.basis_digest,
            as_of_utc=self.world.query.as_of_utc,
            known_at_utc=self.world.query.known_at_utc,
            base_currency=self.world.query.base_currency,
        )

    def test_worker_derives_position_and_price_from_capital_world(self) -> None:
        self.assertNotEqual(
            self.intent.reference_price,
            self.admission.verified_reference_price,
        )
        result = execute_paper_effect_worker(
            self._worker_request(),
            principal_id=self.operator.principal.principal_id,
            agent_runtime_id=self.operator.agent_runtime.agent_runtime_id,
        )
        execution = self.store.read_effect_execution(result.execution_id)
        self.assertEqual(result.domain_outcome, "completed")
        self.assertEqual(execution.state, "completed")
        self.assertIsNotNone(execution.execution_report_id)
        self.assertIsNotNone(execution.reconciliation_id)

    def test_runtime_request_binds_authenticated_principal_and_agent(self) -> None:
        port = CapitalRuntimePort(
            runtime_binary=self.root / "runtime",
            runner_binary=self.root / "runner",
            runtime_root=self.root / "runtime-state",
            working_root=self.root,
        )
        payload, principal_id, agent_id = port.build_paper_effect_request(
            operator=self.operator,
            store=self.store,
            effect_intent_id=self.intent.effect_intent_id,
            admission_id=self.admission.admission_id,
            state_db_path=self.state_db,
            receipt_root=self.receipts / "execution",
            current_world=self.world,
        )
        self.assertEqual(payload["principalId"], principal_id)
        self.assertEqual(payload["agentRuntimeId"], agent_id)
        self.assertEqual(payload["operationKind"], "paper_effect.execute")
        self.assertNotIn("executable", payload)
        self.assertNotIn("env", payload)

    def test_runtime_request_rejects_identity_substitution(self) -> None:
        wrong = self.operator.model_copy(
            update={
                "agent_runtime": AgentRuntimeIdentity(
                    agent_runtime_id="agent:other",
                    principal_id=self.operator.principal.principal_id,
                    provider_id="test-provider",
                )
            }
        )
        port = CapitalRuntimePort(
            runtime_binary=self.root / "runtime",
            runner_binary=self.root / "runner",
            runtime_root=self.root / "runtime-state",
            working_root=self.root,
        )
        with self.assertRaisesRegex(ValueError, "cross-agent substitution denied"):
            port.build_paper_effect_request(
                operator=wrong,
                store=self.store,
                effect_intent_id=self.intent.effect_intent_id,
                admission_id=self.admission.admission_id,
                state_db_path=self.state_db,
                receipt_root=self.receipts / "execution",
                current_world=self.world,
            )


if __name__ == "__main__":
    unittest.main()
