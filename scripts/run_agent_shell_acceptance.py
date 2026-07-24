#!/usr/bin/env python3
"""Prove the first local Agent Shell journey through the real Runtime."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from finharness.agent_shell import AgentShellService, ensure_local_paper_execution
from finharness.api.app import create_app
from finharness.capital_agent import CapitalAgentStore
from finharness.capital_runtime import CapitalRuntimePort
from finharness.identity import (
    AgentRuntimeIdentity,
    OperatorContext,
    PrincipalIdentity,
    StaticIdentityProvider,
)
from finharness.personal_finance import ingest_personal_finance_export
from finharness.project_paths import ROOT
from finharness.statecore.store import init_state_core


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _write_fixture(path: Path, *, at: str) -> None:
    template = (ROOT / "tests/fixtures/capital_review/admitted.csv.template").read_text(
        encoding="utf-8"
    )
    path.write_text(
        template.replace("{{AS_OF_UTC}}", at).replace("{{VALUED_AT_UTC}}", at),
        encoding="utf-8",
    )


def _binding(client: TestClient) -> str:
    response = client.get("/identity/browser-mutation-binding")
    _require(response.status_code == 200, response.text)
    return str(response.json()["binding_id"])


def _post(client: TestClient, path: str, body: dict[str, object], key: str):
    return client.post(
        path,
        json=body,
        headers={
            "Idempotency-Key": key,
            "X-FinHarness-Browser-Mutation-Binding": _binding(client),
        },
    )


def run_acceptance() -> dict[str, object]:
    runtime_binary = ROOT / "target/debug/finharness-runtime"
    runner_binary = ROOT / "target/debug/finharness-task-runner"
    _require(runtime_binary.is_file(), "finharness-runtime is not built")
    _require(runner_binary.is_file(), "finharness-task-runner is not built")

    with tempfile.TemporaryDirectory(prefix="finharness-agent-shell-") as tmp:
        root = Path(tmp)
        state_db = root / "state.sqlite"
        receipts = root / "receipts"
        engine = init_state_core(state_db)
        observed = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        source = root / "capital.csv"
        _write_fixture(source, at=observed)
        ingest_personal_finance_export(
            source,
            engine=engine,
            receipt_root=receipts / "imports",
        )
        ensure_local_paper_execution(engine)
        identity = OperatorContext(
            principal=PrincipalIdentity(
                principal_id="principal:agent-shell-acceptance",
                provider_id="acceptance",
                principal_kind="human",
                display_label="Agent Shell acceptance",
            ),
            agent_runtime=AgentRuntimeIdentity(
                agent_runtime_id="agent:agent-shell-acceptance",
                principal_id="principal:agent-shell-acceptance",
                provider_id="acceptance",
                agent_profile="local-capital-agent",
            ),
            authentication_method="acceptance_static_session",
            authenticated_at_utc=datetime.now(UTC).isoformat(),
            authentication_epoch_id="agent-shell-acceptance-epoch",
            authentication_expires_at_utc="2099-12-31T23:59:59+00:00",
        )
        port = CapitalRuntimePort(
            runtime_binary=runtime_binary,
            runner_binary=runner_binary,
            runtime_root=root / "runtime",
            working_root=root / "runtime-work",
        )
        (root / "runtime-work").mkdir(parents=True, exist_ok=True)
        service = AgentShellService(
            agent_store=CapitalAgentStore(root / "agent"),
            shell_root=root / "shell",
            state_db_path=state_db,
            execution_receipt_root=receipts / "execution",
            runtime_port=port,
            model_name="acceptance-no-provider-call",
        )
        app = create_app(
            state_core_engine=engine,
            receipt_root=str(receipts / "state"),
            identity_provider=StaticIdentityProvider(identity),
            agent_shell_service=service,
        )
        client = TestClient(app)

        bootstrap = client.get("/agent/bootstrap")
        _require(bootstrap.status_code == 200, bootstrap.text)
        boot = bootstrap.json()
        _require(boot["world"]["status"] == "admitted", "World is not admitted")
        _require(boot["runtime_available"] is True, "Runtime is unavailable")
        _require(boot["browser_secret_input_allowed"] is False, "browser secret input opened")
        _require(boot["live_execution_allowed"] is False, "live execution opened")

        mission_key = "mission:agent-shell:acceptance"
        mission_body: dict[str, object] = {
            "request_id": mission_key,
            "objective": "Reduce concentration with one recoverable paper Effect",
            "success_conditions": ["One paper Effect is reconciled exactly once"],
            "liquidity_floor": "1000",
            "max_simulated_notional": "3000",
            "delegation_max_notional": "2500",
            "delegation_max_uses": 3,
            "delegation_ttl_minutes": 1440,
            "initial_belief": "SPY concentration may exceed the intended boundary",
            "belief_confidence": "0.5",
            "belief_review_condition": "Review if Capital World identity changes",
        }
        first_mission = _post(client, "/agent/missions", mission_body, mission_key)
        replay_mission = _post(client, "/agent/missions", mission_body, mission_key)
        _require(first_mission.status_code == 201, first_mission.text)
        _require(replay_mission.status_code == 201, replay_mission.text)
        _require(first_mission.json() == replay_mission.json(), "Mission replay drifted")
        _require(
            replay_mission.headers.get("X-FinHarness-Idempotent-Replay") == "true",
            "Mission did not replay through the identity protocol",
        )
        mission_id = str(first_mission.json()["mission"]["mission_id"])

        message_key = "message:agent-shell:acceptance"
        message_body: dict[str, object] = {
            "request_id": message_key,
            "message": "What is known and uncertain before a paper test?",
        }
        message = _post(
            client,
            f"/agent/missions/{mission_id}/messages",
            message_body,
            message_key,
        )
        _require(message.status_code == 200, message.text)
        _require(message.json()["execution_allowed"] is False, "chat gained execution")

        effect_key = "effect:agent-shell:acceptance"
        effect_body: dict[str, object] = {
            "request_id": effect_key,
            "symbol": "SPY",
            "side": "sell",
            "quantity": "1",
            "rationale": "Bounded product-shell paper test",
        }
        first_effect = _post(
            client,
            f"/agent/missions/{mission_id}/paper-effects",
            effect_body,
            effect_key,
        )
        replay_effect = _post(
            client,
            f"/agent/missions/{mission_id}/paper-effects",
            effect_body,
            effect_key,
        )
        _require(first_effect.status_code == 200, first_effect.text)
        _require(replay_effect.status_code == 200, replay_effect.text)
        _require(first_effect.json() == replay_effect.json(), "Effect replay drifted")
        effect = first_effect.json()
        _require(effect["verified_reference_price"] == "1000", "World price not used")
        _require(effect["runtime"]["status"] == "succeeded", "Runtime Job failed")
        _require(effect["execution"]["state"] == "completed", "Effect did not complete")
        _require(effect["live_execution_allowed"] is False, "live execution opened")
        _require(
            replay_effect.headers.get("X-FinHarness-Idempotent-Replay") == "true",
            "Effect did not replay through the identity protocol",
        )

        ui = client.get("/agent-ui/")
        _require(ui.status_code == 200, "Agent UI is not mounted")
        _require("FinHarness Agent" in ui.text, "Agent UI body is incorrect")
        engine.dispose()
        return {
            "ok": True,
            "mission_id": mission_id,
            "runtime_job_id": effect["runtime"]["jobId"],
            "runtime_attempt_id": effect["runtime"]["attemptId"],
            "effect_execution_id": effect["execution"]["execution_id"],
            "mission_replay": True,
            "effect_replay": True,
            "conversation_execution_allowed": False,
            "browser_secret_input_allowed": False,
            "verified_reference_price": effect["verified_reference_price"],
            "live_execution_allowed": False,
        }


def main() -> int:
    print(json.dumps(run_acceptance(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
