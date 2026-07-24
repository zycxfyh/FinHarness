#!/usr/bin/env python3
"""Crash the Agent Shell after Runtime completion and recover across API restart."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from http.client import HTTPConnection, RemoteDisconnected
from pathlib import Path
from typing import Any, cast

from agent_shell_fixture_runtime import (
    FixtureRuntimeMode,
    ResolvedFixtureRuntimeMode,
    build_fixture_runtime_port,
    resolve_fixture_runtime_mode,
)
from finharness.agent_shell import AgentShellService
from finharness.api.identity_mutation_reconciliation import (
    reconcile_identity_mutation_from_domain_truth,
)
from finharness.capital_agent import CapitalAgentStore
from finharness.project_paths import ROOT
from finharness.statecore.store import init_state_core


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _json_request(
    port: int,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    payload = None if body is None else json.dumps(body).encode()
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
    connection = HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        connection.request(
            method,
            path,
            body=payload,
            headers=request_headers,
        )
        response = connection.getresponse()
        raw = response.read()
        parsed = json.loads(raw) if raw else {}
        return response.status, parsed, dict(response.getheaders())
    finally:
        connection.close()


def _wait_ready(port: int, process: subprocess.Popen[bytes]) -> None:
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError(f"fixture server exited early: {process.returncode}")
        try:
            status, _payload, _headers = _json_request(port, "/agent/bootstrap", timeout=1)
            if status == 200:
                return
        except (ConnectionRefusedError, RemoteDisconnected, TimeoutError, OSError):
            pass
        time.sleep(0.1)
    raise RuntimeError("fixture server did not become ready")


def _start(
    root: Path,
    port: int,
    *,
    crash: bool,
    runtime_mode: ResolvedFixtureRuntimeMode,
) -> subprocess.Popen[bytes]:
    command = [
        sys.executable,
        "scripts/serve_agent_shell_test_fixture.py",
        "--root",
        str(root),
        "--port",
        str(port),
    ]
    command.extend(("--runtime-mode", runtime_mode))
    if crash:
        command.append("--crash-after-runtime")
    log = (root / ("crash-server.log" if crash else "restart-server.log")).open("wb")
    return subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)


def _binding(port: int) -> str:
    status, payload, _headers = _json_request(port, "/identity/browser-mutation-binding")
    if status != 200:
        raise RuntimeError(f"binding failed: {status} {payload}")
    return str(payload["binding_id"])


def _post(
    port: int,
    path: str,
    body: dict[str, object],
    key: str,
    *,
    timeout: float = 15,
) -> tuple[int, dict[str, Any], dict[str, str]]:
    return _json_request(
        port,
        path,
        method="POST",
        body=body,
        headers={
            "Idempotency-Key": key,
            "X-FinHarness-Browser-Mutation-Binding": _binding(port),
        },
        timeout=timeout,
    )


def _pending_identity_receipt(root: Path) -> Path:
    pending: list[Path] = []
    for path in (root / "receipts/state/identity").glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("state") == "pending":
            pending.append(path)
    if len(pending) != 1:
        raise RuntimeError(f"expected one pending identity receipt, found {pending}")
    return pending[0]


def _requested_runtime_mode() -> ResolvedFixtureRuntimeMode:
    requested = os.environ.get("FINHARNESS_AGENT_FIXTURE_RUNTIME_MODE", "auto")
    if requested not in {"auto", "fixture", "systemd"}:
        raise RuntimeError(
            "FINHARNESS_AGENT_FIXTURE_RUNTIME_MODE must be auto, fixture, or systemd"
        )
    return resolve_fixture_runtime_mode(cast(FixtureRuntimeMode, requested))


def run_acceptance() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="finharness-agent-process-recovery-") as tmp:
        root = Path(tmp)
        port = _port()
        runtime_mode = _requested_runtime_mode()
        first = _start(root, port, crash=True, runtime_mode=runtime_mode)
        try:
            _wait_ready(port, first)
            mission_key = "mission:process-recovery:0001"
            mission_body: dict[str, object] = {
                "request_id": mission_key,
                "objective": "Prove process-level paper Effect recovery",
                "success_conditions": ["The same Runtime Job is replayed after restart"],
                "liquidity_floor": "1000",
                "max_simulated_notional": "3000",
                "delegation_max_notional": "2500",
                "delegation_max_uses": 3,
                "delegation_ttl_minutes": 1440,
                "initial_belief": "The recovery path should preserve one Effect",
                "belief_confidence": "0.5",
                "belief_review_condition": "Review after API restart",
            }
            status, mission, _headers = _post(port, "/agent/missions", mission_body, mission_key)
            if status != 201:
                raise RuntimeError(f"Mission failed: {status} {mission}")
            mission_id = str(mission["mission"]["mission_id"])
            effect_key = "effect:process-recovery:0001"
            effect_body: dict[str, object] = {
                "request_id": effect_key,
                "symbol": "SPY",
                "side": "sell",
                "quantity": "1",
                "rationale": "Crash after Runtime completion",
            }
            try:
                _post(
                    port,
                    f"/agent/missions/{mission_id}/paper-effects",
                    effect_body,
                    effect_key,
                    timeout=20,
                )
                raise RuntimeError("effect request unexpectedly returned before process crash")
            except (ConnectionRefusedError, RemoteDisconnected, TimeoutError, OSError):
                pass
            first.wait(timeout=15)
            if first.returncode != 86:
                raise RuntimeError(f"unexpected crash exit code: {first.returncode}")
            pending_path = _pending_identity_receipt(root)
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
            domain_path = (
                root / "receipts/state/agent-shell-effects" / f"{pending['receipt_id']}.json"
            )
            domain = json.loads(domain_path.read_text(encoding="utf-8"))
            if domain.get("state") != "pending":
                raise RuntimeError("domain receipt did not survive as pending")

            second = _start(root, port, crash=False, runtime_mode=runtime_mode)
            try:
                _wait_ready(port, second)
                engine = init_state_core(root / "state.sqlite")
                service = AgentShellService(
                    agent_store=CapitalAgentStore(root / "agent"),
                    shell_root=root / "shell",
                    state_db_path=root / "state.sqlite",
                    execution_receipt_root=root / "receipts/execution",
                    runtime_port=build_fixture_runtime_port(
                        root,
                        mode=runtime_mode,
                    )[1],
                )
                reconciled = reconcile_identity_mutation_from_domain_truth(
                    pending_path,
                    engine=engine,
                    receipt_root=root / "receipts/state",
                    reconciled_by="process-recovery-acceptance",
                    reason="Verified persisted Runtime and StateCore truth after API restart.",
                    resolver_services={"agent_shell_service": service},
                )
                if reconciled.get("state") != "reconciled_applied":
                    raise RuntimeError(f"reconciliation failed: {reconciled}")
                status, replay, headers = _post(
                    port,
                    f"/agent/missions/{mission_id}/paper-effects",
                    effect_body,
                    effect_key,
                )
                if status != 200:
                    raise RuntimeError(f"replay failed: {status} {replay}")
                if headers.get("X-Finharness-Idempotent-Replay", "").lower() != "true":
                    # urllib normalizes capitalization differently across versions.
                    replay_header = next(
                        (
                            value
                            for name, value in headers.items()
                            if name.lower() == "x-finharness-idempotent-replay"
                        ),
                        "",
                    )
                    if replay_header.lower() != "true":
                        raise RuntimeError("HTTP replay header is missing")
                executions = list((root / "agent/effect-executions").glob("*.json"))
                intents = list((root / "agent/effect-intents").glob("*.json"))
                if len(executions) != 1 or len(intents) != 1:
                    raise RuntimeError("restart created duplicate Effect artifacts")
                engine.dispose()
                return {
                    "ok": True,
                    "runtime_mode": runtime_mode,
                    "crash_exit_code": first.returncode,
                    "identity_state_before_recovery": "pending",
                    "domain_state_before_recovery": "pending",
                    "reconciliation_state": reconciled["state"],
                    "runtime_job_id": replay["runtime"]["jobId"],
                    "effect_execution_id": replay["execution"]["execution_id"],
                    "effect_intent_count": len(intents),
                    "effect_execution_count": len(executions),
                    "same_key_replay": True,
                    "live_execution_allowed": replay["live_execution_allowed"],
                }
            finally:
                second.terminate()
                try:
                    second.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    second.kill()
        finally:
            if first.poll() is None:
                first.kill()


def main() -> int:
    report = run_acceptance()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
