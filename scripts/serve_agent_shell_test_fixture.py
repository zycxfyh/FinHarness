#!/usr/bin/env python3
"""Serve a persisted Agent Shell fixture for process and browser acceptance."""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import uvicorn

from agent_shell_fixture_runtime import (
    FixtureRuntimeMode,
    build_fixture_runtime_port,
)
from finharness.agent_shell import AgentShellService, ensure_local_paper_execution
from finharness.api.app import create_app
from finharness.capital_agent import CapitalAgentStore
from finharness.identity import (
    AgentRuntimeIdentity,
    OperatorContext,
    PrincipalIdentity,
    StaticIdentityProvider,
)
from finharness.personal_finance import ingest_personal_finance_export
from finharness.project_paths import ROOT
from finharness.statecore.store import init_state_core


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--crash-after-runtime", action="store_true")
    parser.add_argument(
        "--runtime-mode",
        choices=("auto", "fixture", "systemd"),
        default="auto",
    )
    return parser


def _write_fixture(path: Path, *, observed_at: str) -> None:
    template = (ROOT / "tests/fixtures/capital_review/admitted.csv.template").read_text(
        encoding="utf-8"
    )
    path.write_text(
        template.replace("{{AS_OF_UTC}}", observed_at).replace("{{VALUED_AT_UTC}}", observed_at),
        encoding="utf-8",
    )


def build_fixture_app(
    root: Path,
    *,
    crash_after_runtime: bool,
    runtime_mode: FixtureRuntimeMode,
):
    root = root.resolve()
    state_db = root / "state.sqlite"
    receipts = root / "receipts"
    source = root / "capital.csv"
    marker = root / "fixture-imported"
    root.mkdir(parents=True, exist_ok=True)
    engine = init_state_core(state_db)
    if not marker.exists():
        _write_fixture(
            source,
            observed_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
        )
        ingest_personal_finance_export(
            source,
            engine=engine,
            receipt_root=receipts / "imports",
        )
        marker.write_text("imported\n", encoding="utf-8")
    ensure_local_paper_execution(engine)
    principal_id = "principal:agent-shell-process-fixture"
    identity = OperatorContext(
        principal=PrincipalIdentity(
            principal_id=principal_id,
            provider_id="agent-shell-process-fixture",
            principal_kind="human",
            display_label="Agent Shell process fixture",
        ),
        agent_runtime=AgentRuntimeIdentity(
            agent_runtime_id="agent:agent-shell-process-fixture",
            principal_id=principal_id,
            provider_id="agent-shell-process-fixture",
            agent_profile="local-capital-agent",
        ),
        authentication_method="process_fixture_static_session",
        authenticated_at_utc=datetime.now(UTC).isoformat(),
        authentication_epoch_id="agent-shell-process-fixture-epoch",
        authentication_expires_at_utc="2099-12-31T23:59:59+00:00",
    )
    resolved_runtime_mode, runtime_port = build_fixture_runtime_port(
        root,
        mode=runtime_mode,
    )

    def crash() -> None:
        os._exit(86)

    service = AgentShellService(
        agent_store=CapitalAgentStore(root / "agent"),
        shell_root=root / "shell",
        state_db_path=state_db,
        execution_receipt_root=receipts / "execution",
        runtime_port=runtime_port,
        model_name="fixture-no-provider-call",
        after_paper_effect_runtime_hook=crash if crash_after_runtime else None,
    )
    app = create_app(
        state_core_engine=engine,
        receipt_root=str(receipts / "state"),
        identity_provider=StaticIdentityProvider(identity),
        agent_shell_service=service,
    )
    app.state.agent_shell_fixture_runtime_mode = resolved_runtime_mode
    return app


def main() -> None:
    args = _parser().parse_args()
    app = build_fixture_app(
        args.root,
        crash_after_runtime=args.crash_after_runtime,
        runtime_mode=args.runtime_mode,
    )
    print(
        "AGENT_SHELL_FIXTURE_READY "
        f"http://127.0.0.1:{args.port} "
        f"runtime={app.state.agent_shell_fixture_runtime_mode}",
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
