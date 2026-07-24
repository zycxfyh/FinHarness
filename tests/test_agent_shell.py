from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from collections.abc import Mapping
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from scripts.reconcile_identity_mutation import main as reconcile_identity_mutation_main
from sqlmodel import Session

from finharness.agent_shell import (
    LOCAL_PAPER_ACCOUNT_ID,
    AgentShellConflictError,
    AgentShellMutationRecoveryRequired,
    AgentShellService,
    MissionConversationReply,
    ensure_local_paper_execution,
)
from finharness.api.app import create_app
from finharness.api.identity_mutation_reconciliation import (
    reconcile_identity_mutation_from_domain_truth,
)
from finharness.capital_agent import CapitalAgentNotFoundError, CapitalAgentStore
from finharness.capital_runtime import RuntimeObservation
from finharness.execution.adapters.simulated_broker import SimulatedBrokerAdapter
from finharness.execution.broker import clear_broker_registry, register_broker_adapter
from finharness.identity import (
    AgentRuntimeIdentity,
    OperatorContext,
    PrincipalIdentity,
    StaticIdentityProvider,
)
from finharness.personal_finance import ingest_personal_finance_export
from finharness.project_paths import ROOT
from finharness.statecore.capital_world import resolve_capital_world
from finharness.statecore.execution_models import ExecutionAccount, ExecutionEnvironment
from finharness.statecore.store import init_state_core


class _FakeRuntimePort:
    def __init__(self) -> None:
        self.calls = 0
        self.observe_calls = 0
        self.observations: dict[str, RuntimeObservation] = {}

    def submit_paper_effect(
        self,
        *,
        operator,
        store,
        effect_intent_id,
        admission_id,
        state_db_path,
        receipt_root,
        current_world,
    ):
        self.calls += 1
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
            job_id = f"job-test-{effect_intent_id[-16:]}"
            attempt_id = f"attempt-test-{effect_intent_id[-16:]}"
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
                stdout_tail="{}",
                stderr_tail="",
                artifacts_available=True,
            )
            self.observations[job_id] = observation
            return observation, execution
        finally:
            clear_broker_registry()
            engine.dispose()

    def observe(self, job_id: str) -> RuntimeObservation:
        self.observe_calls += 1
        return self.observations[job_id]


def _write_fixture(path: Path, *, at: str) -> None:
    template = (ROOT / "tests/fixtures/capital_review/admitted.csv.template").read_text(
        encoding="utf-8"
    )
    path.write_text(
        template.replace("{{AS_OF_UTC}}", at).replace("{{VALUED_AT_UTC}}", at),
        encoding="utf-8",
    )


class AgentShellApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state_db = self.root / "state.sqlite"
        self.engine = init_state_core(self.state_db)
        self.addCleanup(self.engine.dispose)
        observed = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        source = self.root / "capital.csv"
        _write_fixture(source, at=observed)
        ingest_personal_finance_export(
            source,
            engine=self.engine,
            receipt_root=self.root / "import-receipts",
        )
        ensure_local_paper_execution(self.engine)
        self.operator = OperatorContext(
            principal=PrincipalIdentity(
                principal_id="principal:agent-shell-test",
                provider_id="test-agent-shell",
                principal_kind="human",
                display_label="Agent Shell Test",
            ),
            agent_runtime=AgentRuntimeIdentity(
                agent_runtime_id="agent:agent-shell-test",
                principal_id="principal:agent-shell-test",
                provider_id="test-agent-shell",
                agent_profile="test",
            ),
            authentication_method="test_static_session",
            authenticated_at_utc=datetime.now(UTC).isoformat(),
            authentication_epoch_id="agent-shell-test-epoch",
            authentication_expires_at_utc="2099-12-31T23:59:59+00:00",
        )
        self.store = CapitalAgentStore(self.root / "agent")
        self.runtime_port = _FakeRuntimePort()
        self.service = AgentShellService(
            agent_store=self.store,
            shell_root=self.root / "shell",
            state_db_path=self.state_db,
            execution_receipt_root=self.root / "execution-receipts",
            runtime_port=self.runtime_port,
            model_name="test-model",
        )
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.root / "state-receipts"),
            identity_provider=StaticIdentityProvider(self.operator),
            agent_shell_service=self.service,
        )
        self.client = TestClient(self.app)

    def _binding(self) -> str:
        response = self.client.get("/identity/browser-mutation-binding")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["binding_id"]

    def _post(self, path: str, body: Mapping[str, object], key: str):
        return self.client.post(
            path,
            json=body,
            headers={
                "Idempotency-Key": key,
                "X-FinHarness-Browser-Mutation-Binding": self._binding(),
            },
        )

    def _identity_receipts(self) -> list[Path]:
        return sorted((self.root / "state-receipts" / "identity").glob("*.json"))

    def _mission_body(self, key: str) -> dict[str, object]:
        return {
            "request_id": key,
            "objective": "Reduce concentration with one bounded paper test",
            "success_conditions": ["The paper Effect is reconciled exactly once"],
            "liquidity_floor": "1000",
            "max_simulated_notional": "3000",
            "delegation_max_notional": "2500",
            "delegation_max_uses": 3,
            "delegation_ttl_minutes": 1440,
            "initial_belief": "SPY concentration may exceed the preferred boundary",
            "belief_confidence": "0.5",
            "belief_review_condition": "Review if Capital World changes",
        }

    def _drifted_world(self):
        current = resolve_capital_world(engine=self.engine, use_case="agent_context")
        return replace(
            current,
            world_id=f"{current.world_id}:drifted",
            basis_digest=f"{current.basis_digest}:drifted",
        )

    def _start_mission(self):
        key = "mission:test:0001"
        response = self._post("/agent/missions", self._mission_body(key), key)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_bootstrap_exposes_identity_model_world_and_no_secret_input(self) -> None:
        response = self.client.get("/agent/bootstrap")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["principal_id"], self.operator.principal.principal_id)
        runtime_identity = self.operator.agent_runtime
        self.assertIsNotNone(runtime_identity)
        assert runtime_identity is not None
        self.assertEqual(
            payload["agent_runtime_id"],
            runtime_identity.agent_runtime_id,
        )
        self.assertEqual(payload["world"]["status"], "admitted")
        self.assertTrue(payload["runtime_available"])
        self.assertTrue(payload["simulated_effect_allowed"])
        self.assertFalse(payload["live_execution_allowed"])
        self.assertFalse(payload["browser_secret_input_allowed"])
        self.assertFalse(payload["model"]["browser_secret_input_allowed"])
        self.assertNotIn("api_key", payload["model"])

    def test_bootstrap_filters_missions_by_agent_runtime_identity(self) -> None:
        mission = self._start_mission()
        other_runtime = AgentRuntimeIdentity(
            agent_runtime_id="agent:agent-shell-test:other",
            principal_id=self.operator.principal.principal_id,
            provider_id="test-agent-shell",
            agent_profile="test",
        )
        other_operator = self.operator.model_copy(update={"agent_runtime": other_runtime})
        other_app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.root / "state-receipts"),
            identity_provider=StaticIdentityProvider(other_operator),
            agent_shell_service=self.service,
        )
        response = TestClient(other_app).get("/agent/bootstrap")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["missions"], [])
        self.assertNotIn(
            mission["mission"]["mission_id"],
            {item["mission_id"] for item in response.json()["missions"]},
        )

    def test_mission_start_is_keyed_and_returns_one_durable_bundle(self) -> None:
        key = "mission:test:0002"
        body = self._mission_body(key)
        first = self._post("/agent/missions", body, key)
        second = self._post("/agent/missions", body, key)
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(second.headers["X-FinHarness-Idempotent-Replay"], "true")
        self.assertEqual(len(self.store.list_missions()), 1)

    def test_conversation_is_read_only_and_keyed(self) -> None:
        mission = self._start_mission()
        key = "message:test:0001"
        path = f"/agent/missions/{mission['mission']['mission_id']}/messages"
        body = {"request_id": key, "message": "What is uncertain right now?"}
        first = self._post(path, body, key)
        second = self._post(path, body, key)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), second.json())
        self.assertFalse(first.json()["execution_allowed"])
        self.assertFalse(first.json()["live_execution_allowed"])
        self.assertEqual(first.json()["model_status"], "unavailable")

    def test_provider_reply_redline_scans_every_user_visible_field(self) -> None:
        mission = self._start_mission()
        mission_id = mission["mission"]["mission_id"]
        world_id = mission["world"]["world_id"]
        basis_digest = mission["world"]["basis_digest"]
        safe = MissionConversationReply(
            turn_id="provider-turn",
            request_id="provider-request",
            mission_id=mission_id,
            world_id=world_id,
            world_basis_digest=basis_digest,
            answer="The current evidence is descriptive only.",
            observations=("SPY is valued in the admitted Capital World.",),
            uncertainties=("Suitability has not been established.",),
            next_steps=("Review the evidence lineage.",),
            model_status="completed",
            model_provider="test-provider",
            model_name="test-model",
            created_at_utc=datetime.now(UTC).isoformat(),
        )
        cases = (
            safe.model_copy(update={"answer": "I recommend selling SPY."}),
            safe.model_copy(update={"next_steps": ("Sell SPY.",)}),
        )
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            for index, candidate in enumerate(cases, start=1):
                with self.subTest(index=index):
                    key = f"message:redline:{index:04d}"
                    path = f"/agent/missions/{mission_id}/messages"
                    with patch(
                        "finharness.agent_shell._run_model_conversation",
                        return_value=candidate,
                    ):
                        response = self._post(
                            path,
                            {"request_id": key, "message": "Assess the evidence."},
                            key,
                        )
                    self.assertEqual(response.status_code, 200, response.text)
                    payload = response.json()
                    self.assertEqual(payload["model_status"], "rejected")
                    self.assertNotIn("recommend selling", payload["answer"].lower())
                    self.assertNotIn("sell spy", " ".join(payload["next_steps"]).lower())

    def test_reserved_paper_account_rejects_incompatible_state(self) -> None:
        for field, incompatible, restored in (
            ("environment", ExecutionEnvironment.LIVE.value, ExecutionEnvironment.PAPER.value),
            ("funded", True, False),
        ):
            with self.subTest(field=field):
                with Session(self.engine) as session:
                    account = session.get(ExecutionAccount, LOCAL_PAPER_ACCOUNT_ID)
                    self.assertIsNotNone(account)
                    assert account is not None
                    setattr(account, field, incompatible)
                    session.add(account)
                    session.commit()
                try:
                    with self.assertRaisesRegex(
                        AgentShellConflictError,
                        "incompatible account",
                    ):
                        ensure_local_paper_execution(self.engine)
                finally:
                    with Session(self.engine) as session:
                        account = session.get(ExecutionAccount, LOCAL_PAPER_ACCOUNT_ID)
                        assert account is not None
                        setattr(account, field, restored)
                        session.add(account)
                        session.commit()

    def test_world_drift_checkpoint_resume_and_effect(self) -> None:
        mission = self._start_mission()
        mission_id = mission["mission"]["mission_id"]
        drifted_world = self._drifted_world()
        with patch(
            "finharness.agent_shell.resolve_capital_world",
            return_value=drifted_world,
        ):
            drift = self.client.get(f"/agent/missions/{mission_id}/world-drift")
            self.assertEqual(drift.status_code, 200, drift.text)
            self.assertTrue(drift.json()["drifted"])
            self.assertTrue(drift.json()["can_checkpoint_and_resume"])

            blocked = self._post(
                f"/agent/missions/{mission_id}/paper-effects",
                {
                    "request_id": "effect:world-drift:blocked",
                    "symbol": "SPY",
                    "side": "sell",
                    "quantity": "1",
                    "rationale": "Must not execute against stale Mission World",
                },
                "effect:world-drift:blocked",
            )
            self.assertEqual(blocked.status_code, 409, blocked.text)
            self.assertEqual(blocked.json()["detail"]["code"], "mission_world_changed")
            self.assertTrue(blocked.json()["detail"]["drift"]["drifted"])

            key = "world-recovery:test:0001"
            body = {
                "request_id": key,
                "action": "checkpoint_and_resume",
                "note": "Accept the newly admitted Capital World.",
            }
            first = self._post(
                f"/agent/missions/{mission_id}/world-recovery",
                body,
                key,
            )
            replay = self._post(
                f"/agent/missions/{mission_id}/world-recovery",
                body,
                key,
            )
            self.assertEqual(first.status_code, 200, first.text)
            self.assertEqual(first.json(), replay.json())
            self.assertEqual(replay.headers["X-FinHarness-Idempotent-Replay"], "true")
            payload = first.json()
            self.assertEqual(payload["mission"]["current_world_id"], drifted_world.world_id)
            self.assertEqual(payload["checkpoint"]["world_id"], drifted_world.world_id)

            current = self.client.get(f"/agent/missions/{mission_id}/world-drift")
            self.assertEqual(current.status_code, 200, current.text)
            self.assertFalse(current.json()["drifted"])

            effect = self._post(
                f"/agent/missions/{mission_id}/paper-effects",
                {
                    "request_id": "effect:world-drift:after-recovery",
                    "symbol": "SPY",
                    "side": "sell",
                    "quantity": "1",
                    "rationale": "Execute only after explicit World recovery",
                },
                "effect:world-drift:after-recovery",
            )
            self.assertEqual(effect.status_code, 200, effect.text)

    def test_paused_mission_world_recovery_resumes_and_allows_effect(self) -> None:
        mission = self._start_mission()
        mission_id = mission["mission"]["mission_id"]
        paused = self.service.agent_store.pause_mission(
            mission_id,
            reason="Pause before accepting a new Capital World.",
        )
        self.assertEqual(paused.state, "paused")
        drifted_world = self._drifted_world()
        key = "world-recovery:paused:0001"
        body = {
            "request_id": key,
            "action": "checkpoint_and_resume",
            "note": "Checkpoint the new World and actually resume the Mission.",
        }
        with patch(
            "finharness.agent_shell.resolve_capital_world",
            return_value=drifted_world,
        ):
            drift = self.client.get(f"/agent/missions/{mission_id}/world-drift")
            self.assertEqual(drift.status_code, 200, drift.text)
            self.assertTrue(drift.json()["can_checkpoint_and_resume"])
            recovered = self._post(
                f"/agent/missions/{mission_id}/world-recovery",
                body,
                key,
            )
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertEqual(recovered.json()["mission"]["state"], "active")
            effect = self._post(
                f"/agent/missions/{mission_id}/paper-effects",
                {
                    "request_id": "effect:paused:after-recovery",
                    "symbol": "SPY",
                    "side": "sell",
                    "quantity": "1",
                    "rationale": "A resumed Mission may use its bounded paper Delegation.",
                },
                "effect:paused:after-recovery",
            )
            self.assertEqual(effect.status_code, 200, effect.text)

    def _pending_world_recovery_before_checkpoint(
        self,
        *,
        key: str,
    ) -> tuple[Path, Path, dict[str, object], str, object]:
        mission = self._start_mission()
        mission_id = mission["mission"]["mission_id"]
        drifted_world = self._drifted_world()
        body: dict[str, object] = {
            "request_id": key,
            "action": "checkpoint_and_resume",
            "note": "Recover deterministically after the pre-checkpoint crash window.",
        }
        before = set(self._identity_receipts())

        def interrupt_after_pending_receipt() -> None:
            raise AgentShellMutationRecoveryRequired(
                "pending-world-recovery-receipt",
                "simulated process loss before checkpoint",
            )

        self.service.after_world_recovery_receipt_hook = interrupt_after_pending_receipt
        try:
            with patch(
                "finharness.agent_shell.resolve_capital_world",
                return_value=drifted_world,
            ):
                first = self._post(
                    f"/agent/missions/{mission_id}/world-recovery",
                    body,
                    key,
                )
        finally:
            self.service.after_world_recovery_receipt_hook = None
        self.assertEqual(first.status_code, 503, first.text)
        pending_paths = sorted(set(self._identity_receipts()) - before)
        self.assertEqual(len(pending_paths), 1)
        pending_path = pending_paths[0]
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        domain_path = (
            self.root
            / "state-receipts"
            / "agent-shell-world-recoveries"
            / f"{pending['receipt_id']}.json"
        )
        domain = json.loads(domain_path.read_text(encoding="utf-8"))
        self.assertEqual(domain["state"], "pending")
        record = domain["record"]
        self.assertIsInstance(record, dict)
        assert isinstance(record, dict)
        checkpoint_path = self.root / "agent" / "checkpoints" / f"{record['checkpoint_id']}.json"
        self.assertFalse(checkpoint_path.exists())
        return pending_path, domain_path, body, mission_id, drifted_world

    def test_pending_world_recovery_applies_missing_checkpoint(self) -> None:
        pending_path, domain_path, body, mission_id, drifted_world = (
            self._pending_world_recovery_before_checkpoint(key="world-recovery:pre-checkpoint:0001")
        )
        with patch(
            "finharness.api.routes_agent_shell.resolve_capital_world",
            return_value=drifted_world,
        ):
            reconciled = reconcile_identity_mutation_from_domain_truth(
                pending_path,
                engine=self.engine,
                receipt_root=self.root / "state-receipts",
                reconciled_by="operator:agent-shell-test",
                reason="Apply the deterministic checkpoint omitted by the crashed process.",
                resolver_services={"agent_shell_service": self.service},
            )
        self.assertEqual(reconciled["state"], "reconciled_applied")
        completed = json.loads(domain_path.read_text(encoding="utf-8"))
        self.assertEqual(completed["state"], "completed")
        self.assertEqual(completed["response"]["mission"]["state"], "active")
        replay = self._post(
            f"/agent/missions/{mission_id}/world-recovery",
            body,
            str(body["request_id"]),
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), completed["response"])

    def test_identity_reconcile_cli_wires_agent_shell_service(self) -> None:
        pending_path, domain_path, _body, _mission_id, drifted_world = (
            self._pending_world_recovery_before_checkpoint(key="world-recovery:cli-wiring:0001")
        )
        output = io.StringIO()
        with (
            patch(
                "finharness.api.routes_agent_shell.resolve_capital_world",
                return_value=drifted_world,
            ),
            redirect_stdout(output),
        ):
            exit_code = reconcile_identity_mutation_main(
                [
                    str(pending_path),
                    "--apply",
                    "--reconciled-by",
                    "operator:cli-test",
                    "--reason",
                    "Prove task identity:reconcile wires the Agent Shell service.",
                    "--state-core-db",
                    str(self.root / "state.sqlite"),
                    "--receipt-root",
                    str(self.root / "state-receipts"),
                    "--agent-root",
                    str(self.root / "agent"),
                    "--shell-root",
                    str(self.root / "shell"),
                    "--runtime-root",
                    str(self.root / "runtime"),
                    "--runtime-working-root",
                    str(self.root / "runtime-work"),
                ]
            )
        self.assertEqual(exit_code, 0, output.getvalue())
        self.assertEqual(
            json.loads(domain_path.read_text(encoding="utf-8"))["state"],
            "completed",
        )

    def _completed_world_recovery_with_pending_identity(
        self,
        *,
        key: str,
    ) -> tuple[Path, dict[str, object], dict[str, object], object]:
        mission = self._start_mission()
        mission_id = mission["mission"]["mission_id"]
        drifted_world = self._drifted_world()
        body: dict[str, object] = {
            "request_id": key,
            "action": "checkpoint_and_resume",
            "note": "Complete the World recovery before outer acknowledgement.",
        }
        before = set(self._identity_receipts())
        with (
            patch(
                "finharness.agent_shell.resolve_capital_world",
                return_value=drifted_world,
            ),
            patch(
                "finharness.api.app.complete_identity_mutation",
                side_effect=OSError("simulated World recovery terminal loss"),
            ),
            TestClient(self.app, raise_server_exceptions=False) as client,
        ):
            binding = client.get("/identity/browser-mutation-binding")
            self.assertEqual(binding.status_code, 200, binding.text)
            first = client.post(
                f"/agent/missions/{mission_id}/world-recovery",
                json=body,
                headers={
                    "Idempotency-Key": key,
                    "X-FinHarness-Browser-Mutation-Binding": binding.json()["binding_id"],
                },
            )
        self.assertEqual(first.status_code, 500)
        pending_paths = sorted(set(self._identity_receipts()) - before)
        self.assertEqual(len(pending_paths), 1)
        pending_path = pending_paths[0]
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        self.assertEqual(pending["state"], "pending")
        domain_path = (
            self.root
            / "state-receipts"
            / "agent-shell-world-recoveries"
            / f"{pending['receipt_id']}.json"
        )
        domain = json.loads(domain_path.read_text(encoding="utf-8"))
        self.assertEqual(domain["state"], "completed")
        return pending_path, domain, body, drifted_world

    def test_completed_world_recovery_revalidates_canonical_artifacts(self) -> None:
        pending_path, domain, body, drifted_world = (
            self._completed_world_recovery_with_pending_identity(
                key="world-recovery:terminal-loss:0001"
            )
        )
        with patch(
            "finharness.api.routes_agent_shell.resolve_capital_world",
            return_value=drifted_world,
        ):
            reconciled = reconcile_identity_mutation_from_domain_truth(
                pending_path,
                engine=self.engine,
                receipt_root=self.root / "state-receipts",
                reconciled_by="operator:agent-shell-test",
                reason="Revalidated completed World recovery against canonical artifacts.",
                resolver_services={"agent_shell_service": self.service},
            )
        self.assertEqual(reconciled["state"], "reconciled_applied")
        response = domain["response"]
        self.assertIsInstance(response, dict)
        assert isinstance(response, dict)
        mission_id = str(response["mission_id"])
        replay = self._post(
            f"/agent/missions/{mission_id}/world-recovery",
            body,
            str(body["request_id"]),
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), response)
        self.assertEqual(replay.headers["X-FinHarness-Idempotent-Replay"], "true")

    def test_completed_world_recovery_rejects_missing_checkpoint(self) -> None:
        pending_path, domain, _body, drifted_world = (
            self._completed_world_recovery_with_pending_identity(
                key="world-recovery:terminal-loss:missing-checkpoint"
            )
        )
        response = domain["response"]
        self.assertIsInstance(response, dict)
        assert isinstance(response, dict)
        checkpoint = response["checkpoint"]
        self.assertIsInstance(checkpoint, dict)
        assert isinstance(checkpoint, dict)
        checkpoint_path = (
            self.root / "agent" / "checkpoints" / f"{checkpoint['checkpoint_id']}.json"
        )
        checkpoint_path.unlink()
        with (
            patch(
                "finharness.api.routes_agent_shell.resolve_capital_world",
                return_value=drifted_world,
            ),
            self.assertRaisesRegex(CapitalAgentNotFoundError, "checkpoints"),
        ):
            reconcile_identity_mutation_from_domain_truth(
                pending_path,
                engine=self.engine,
                receipt_root=self.root / "state-receipts",
                reconciled_by="operator:agent-shell-test",
                reason="Must fail when the canonical checkpoint is missing.",
                resolver_services={"agent_shell_service": self.service},
            )
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        self.assertEqual(pending["state"], "pending")

    def test_world_recovery_receipt_loss_is_typed_reconcilable(self) -> None:
        mission = self._start_mission()
        mission_id = mission["mission"]["mission_id"]
        drifted_world = self._drifted_world()
        key = "world-recovery:receipt-loss:0001"
        body = {
            "request_id": key,
            "action": "checkpoint_and_resume",
            "note": "Recover a completed World checkpoint receipt.",
        }
        before = set(self._identity_receipts())
        with (
            patch(
                "finharness.agent_shell.resolve_capital_world",
                return_value=drifted_world,
            ),
            patch(
                "finharness.agent_shell._complete_world_recovery_domain_receipt",
                side_effect=OSError("simulated World receipt completion loss"),
            ),
        ):
            first = self._post(
                f"/agent/missions/{mission_id}/world-recovery",
                body,
                key,
            )
        self.assertEqual(first.status_code, 503, first.text)
        pending_paths = sorted(set(self._identity_receipts()) - before)
        self.assertEqual(len(pending_paths), 1)
        pending_path = pending_paths[0]
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        self.assertEqual(pending["state"], "pending")
        domain_path = (
            self.root
            / "state-receipts"
            / "agent-shell-world-recoveries"
            / f"{pending['receipt_id']}.json"
        )
        domain = json.loads(domain_path.read_text(encoding="utf-8"))
        self.assertEqual(domain["state"], "pending")

        with patch(
            "finharness.api.routes_agent_shell.resolve_capital_world",
            return_value=drifted_world,
        ):
            reconciled = reconcile_identity_mutation_from_domain_truth(
                pending_path,
                engine=self.engine,
                receipt_root=self.root / "state-receipts",
                reconciled_by="operator:agent-shell-test",
                reason="Verified deterministic Mission checkpoint and World baseline.",
                resolver_services={"agent_shell_service": self.service},
            )
        self.assertEqual(reconciled["state"], "reconciled_applied")
        completed = json.loads(domain_path.read_text(encoding="utf-8"))
        self.assertEqual(completed["state"], "completed")
        replay = self._post(
            f"/agent/missions/{mission_id}/world-recovery",
            body,
            key,
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), completed["response"])
        self.assertEqual(replay.headers["X-FinHarness-Idempotent-Replay"], "true")

    def test_paper_effect_domain_receipt_failure_stays_pending_and_recovers(
        self,
    ) -> None:
        mission = self._start_mission()
        mission_id = mission["mission"]["mission_id"]
        key = "effect:domain-receipt-loss:0001"
        path = f"/agent/missions/{mission_id}/paper-effects"
        body = {
            "request_id": key,
            "symbol": "SPY",
            "side": "sell",
            "quantity": "1",
            "rationale": "Prove recovery when domain receipt completion fails",
        }
        before = set(self._identity_receipts())
        with patch(
            "finharness.agent_shell.durable_compare_and_swap_json",
            return_value=False,
        ):
            first = self._post(path, body, key)
        self.assertEqual(first.status_code, 503, first.text)
        self.assertEqual(
            first.json()["detail"]["code"],
            "agent_shell_mutation_recovery_required",
        )
        pending_paths = sorted(set(self._identity_receipts()) - before)
        self.assertEqual(len(pending_paths), 1)
        pending_path = pending_paths[0]
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        self.assertEqual(pending["state"], "pending")
        domain_path = (
            self.root / "state-receipts" / "agent-shell-effects" / f"{pending['receipt_id']}.json"
        )
        domain = json.loads(domain_path.read_text(encoding="utf-8"))
        self.assertEqual(domain["state"], "pending")
        self.assertIsNone(domain["response"])
        self.assertEqual(self.runtime_port.calls, 1)

        reconciled = reconcile_identity_mutation_from_domain_truth(
            pending_path,
            engine=self.engine,
            receipt_root=self.root / "state-receipts",
            reconciled_by="operator:agent-shell-test",
            reason="Recovered completed Runtime truth after domain receipt failure.",
            resolver_services={"agent_shell_service": self.service},
        )
        self.assertEqual(reconciled["state"], "reconciled_applied")
        completed_domain = json.loads(domain_path.read_text(encoding="utf-8"))
        self.assertEqual(completed_domain["state"], "completed")
        self.assertIsInstance(completed_domain["response"], dict)
        replay = self._post(path, body, key)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.headers["X-FinHarness-Idempotent-Replay"], "true")
        self.assertEqual(replay.json(), completed_domain["response"])
        self.assertEqual(self.runtime_port.calls, 1)
        self.assertEqual(self.runtime_port.observe_calls, 1)

    def test_paper_effect_typed_reconciliation_recovers_terminal_receipt_loss(
        self,
    ) -> None:
        mission = self._start_mission()
        mission_id = mission["mission"]["mission_id"]
        key = "effect:terminal-loss:0001"
        path = f"/agent/missions/{mission_id}/paper-effects"
        body = {
            "request_id": key,
            "symbol": "SPY",
            "side": "sell",
            "quantity": "1",
            "rationale": "Prove typed recovery after terminal receipt loss",
        }
        before = set(self._identity_receipts())
        with (
            patch(
                "finharness.api.app.complete_identity_mutation",
                side_effect=OSError("simulated terminal receipt loss"),
            ),
            TestClient(self.app, raise_server_exceptions=False) as client,
        ):
            binding = client.get("/identity/browser-mutation-binding")
            self.assertEqual(binding.status_code, 200, binding.text)
            first = client.post(
                path,
                json=body,
                headers={
                    "Idempotency-Key": key,
                    "X-FinHarness-Browser-Mutation-Binding": binding.json()["binding_id"],
                },
            )
        self.assertEqual(first.status_code, 500)
        after = set(self._identity_receipts())
        pending_paths = sorted(after - before)
        self.assertEqual(len(pending_paths), 1)
        pending_path = pending_paths[0]
        pending = json.loads(pending_path.read_text(encoding="utf-8"))
        self.assertEqual(pending["state"], "pending")
        self.assertEqual(self.runtime_port.calls, 1)
        domain_path = (
            self.root / "state-receipts" / "agent-shell-effects" / (f"{pending['receipt_id']}.json")
        )
        self.assertTrue(domain_path.is_file())
        domain = json.loads(domain_path.read_text(encoding="utf-8"))

        reconciled = reconcile_identity_mutation_from_domain_truth(
            pending_path,
            engine=self.engine,
            receipt_root=self.root / "state-receipts",
            reconciled_by="operator:agent-shell-test",
            reason="Verified completed Runtime and StateCore execution truth.",
            resolver_services={"agent_shell_service": self.service},
        )
        self.assertEqual(reconciled["state"], "reconciled_applied")
        replay = self._post(path, body, key)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.headers["X-FinHarness-Idempotent-Replay"], "true")
        self.assertEqual(replay.json(), domain["response"])
        self.assertEqual(self.runtime_port.calls, 1)

    def test_paper_effect_uses_world_price_and_replays_one_execution(self) -> None:
        mission = self._start_mission()
        mission_id = mission["mission"]["mission_id"]
        key = "effect:test:0001"
        path = f"/agent/missions/{mission_id}/paper-effects"
        body = {
            "request_id": key,
            "symbol": "SPY",
            "side": "sell",
            "quantity": "1",
            "rationale": "Bounded paper test",
        }
        first = self._post(path, body, key)
        second = self._post(path, body, key)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json(), second.json())
        payload = first.json()
        self.assertEqual(payload["runtime"]["status"], "succeeded")
        self.assertEqual(payload["execution"]["state"], "completed")
        self.assertEqual(payload["verified_reference_price"], "1000")
        self.assertFalse(payload["live_execution_allowed"])
        self.assertEqual(second.headers["X-FinHarness-Idempotent-Replay"], "true")

    def test_agent_ui_is_mounted(self) -> None:
        response = self.client.get("/agent-ui/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("FinHarness Agent", response.text)


class AgentShellAuthenticationTest(unittest.TestCase):
    def test_bootstrap_requires_authenticated_agent_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = init_state_core(root / "state.sqlite")
            service = AgentShellService(
                agent_store=CapitalAgentStore(root / "agent"),
                shell_root=root / "shell",
                state_db_path=root / "state.sqlite",
                execution_receipt_root=root / "execution-receipts",
            )
            app = create_app(
                state_core_engine=engine,
                agent_shell_service=service,
            )
            response = TestClient(app).get("/agent/bootstrap")
            engine.dispose()
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
