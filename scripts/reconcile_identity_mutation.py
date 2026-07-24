"""Inspect or reconcile a pending API mutation from domain truth."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finharness.agent_shell import AgentShellService
from finharness.api.identity_mutation_reconciliation import (
    identity_mutation_reconciliation_resolver_id,
    reconcile_identity_mutation_from_domain_truth,
)
from finharness.capital_agent import CapitalAgentStore
from finharness.capital_runtime import CapitalRuntimePort
from finharness.identity import (
    IdentityMutationError,
    load_identity_mutation_receipt,
)
from finharness.project_paths import ROOT
from finharness.statecore.store import (
    open_state_core,
    state_core_db_path,
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reconciled-by")
    parser.add_argument("--reason")
    parser.add_argument(
        "--state-core-db",
        type=Path,
        default=state_core_db_path(),
    )
    parser.add_argument(
        "--receipt-root",
        type=Path,
        help=("StateCore receipt root. Defaults to the parent of the identity receipt directory."),
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
    args = parser.parse_args(argv)

    try:
        current = load_identity_mutation_receipt(args.receipt)
        request_binding = current.get("request", {})
        resolver = identity_mutation_reconciliation_resolver_id(current)

        if not args.apply:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "dry_run": True,
                        "receipt_id": current.get("receipt_id"),
                        "state": current.get("state"),
                        "request": request_binding,
                        "resolver": resolver,
                        "execution_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if not args.reconciled_by or not args.reason:
            parser.error("--apply requires --reconciled-by and --reason")
        if resolver is None:
            raise IdentityMutationError("no typed reconciliation resolver for this mutation route")

        receipt_root = (
            args.receipt_root if args.receipt_root is not None else args.receipt.parent.parent
        )
        runtime_binary = ROOT / "target" / "debug" / "finharness-runtime"
        runner_binary = ROOT / "target" / "debug" / "finharness-task-runner"
        runtime_port = None
        if runtime_binary.is_file() and runner_binary.is_file():
            runtime_port = CapitalRuntimePort(
                runtime_binary=runtime_binary,
                runner_binary=runner_binary,
                runtime_root=args.runtime_root.resolve(),
                working_root=args.runtime_working_root.resolve(),
            )
        service = AgentShellService(
            agent_store=CapitalAgentStore(args.agent_root.resolve()),
            shell_root=args.shell_root.resolve(),
            state_db_path=args.state_core_db.resolve(),
            execution_receipt_root=receipt_root / "execution",
            runtime_port=runtime_port,
        )
        engine = open_state_core(args.state_core_db)
        try:
            result = reconcile_identity_mutation_from_domain_truth(
                args.receipt,
                engine=engine,
                receipt_root=receipt_root,
                reconciled_by=args.reconciled_by,
                reason=args.reason,
                resolver_services={"agent_shell_service": service},
            )
        finally:
            engine.dispose()

    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "execution_allowed": False,
                }
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": False,
                "receipt_id": result["receipt_id"],
                "state": result["state"],
                "reconciliation": result["reconciliation"],
                "execution_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
