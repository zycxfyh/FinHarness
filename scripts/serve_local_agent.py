#!/usr/bin/env python3
"""Serve the authenticated local FinHarness Agent Shell on loopback."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import uvicorn

from finharness.agent_shell import AgentShellService, ensure_local_paper_execution
from finharness.api.app import create_app
from finharness.api.dependencies import DEFAULT_STATE_CORE_RECEIPT_ROOT
from finharness.capital_agent import CapitalAgentStore
from finharness.capital_runtime import CapitalRuntimePort
from finharness.identity import (
    AgentRuntimeIdentity,
    OperatorContext,
    PrincipalIdentity,
    StaticIdentityProvider,
)
from finharness.project_paths import ROOT
from finharness.statecore.store import DEFAULT_STATE_CORE_DB_PATH, init_state_core

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_CORE_DB_PATH)
    parser.add_argument(
        "--receipt-root",
        type=Path,
        default=DEFAULT_STATE_CORE_RECEIPT_ROOT,
    )
    parser.add_argument(
        "--agent-root",
        type=Path,
        default=ROOT / ".artifacts" / "capital-agent",
    )
    parser.add_argument(
        "--shell-root",
        type=Path,
        default=ROOT / ".artifacts" / "agent-shell",
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=ROOT / ".artifacts" / "agent-runtime",
    )
    parser.add_argument(
        "--runtime-working-root",
        type=Path,
        default=ROOT / ".artifacts" / "agent-runtime-work",
    )
    parser.add_argument("--operator-id", default="local-human")
    parser.add_argument("--agent-id", default=None)
    parser.add_argument("--model", default=None)
    return parser


def build_app(args: argparse.Namespace):
    if args.host not in _LOOPBACK_HOSTS:
        raise SystemExit("local Agent Shell may only bind to a loopback host")
    runtime_binary = ROOT / "target" / "debug" / "finharness-runtime"
    runner_binary = ROOT / "target" / "debug" / "finharness-task-runner"
    if not runtime_binary.is_file() or not runner_binary.is_file():
        raise SystemExit("FinHarness Runtime binaries are missing; run `task runtime:build` first")
    state_db = args.state_db.resolve()
    receipt_root = args.receipt_root.resolve()
    agent_root = args.agent_root.resolve()
    shell_root = args.shell_root.resolve()
    runtime_root = args.runtime_root.resolve()
    working_root = args.runtime_working_root.resolve()
    for path in (receipt_root, agent_root, shell_root, runtime_root, working_root):
        path.mkdir(parents=True, exist_ok=True)

    engine = init_state_core(state_db)
    ensure_local_paper_execution(engine)
    operator_label = args.operator_id.strip()
    if not operator_label:
        raise SystemExit("operator-id must be non-empty")
    principal_id = f"local-human:{operator_label}"
    agent_runtime_id = args.agent_id or f"agent:local:{operator_label}"
    identity = OperatorContext(
        principal=PrincipalIdentity(
            principal_id=principal_id,
            provider_id="finharness-local-agent",
            principal_kind="human",
            display_label=operator_label,
        ),
        agent_runtime=AgentRuntimeIdentity(
            agent_runtime_id=agent_runtime_id,
            principal_id=principal_id,
            provider_id="finharness-local-agent",
            agent_profile="local-capital-agent",
        ),
        authentication_method="loopback_static_agent_session",
        authenticated_at_utc=datetime.now(UTC).isoformat(),
        authentication_epoch_id=f"local-agent:{operator_label}:epoch-v1",
        authentication_expires_at_utc="2099-12-31T23:59:59+00:00",
    )
    service = AgentShellService(
        agent_store=CapitalAgentStore(agent_root),
        shell_root=shell_root,
        state_db_path=state_db,
        execution_receipt_root=receipt_root / "execution",
        runtime_port=CapitalRuntimePort(
            runtime_binary=runtime_binary,
            runner_binary=runner_binary,
            runtime_root=runtime_root,
            working_root=working_root,
        ),
        model_name=args.model,
    )
    return create_app(
        state_core_engine=engine,
        receipt_root=str(receipt_root),
        identity_provider=StaticIdentityProvider(identity),
        agent_shell_service=service,
    )


def main() -> None:
    args = _parser().parse_args()
    app = build_app(args)
    print(
        f"FinHarness Agent Shell: http://{args.host}:{args.port}/agent-ui/; "
        "offline simulated Effects only; live_execution_allowed=false",
        flush=True,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
