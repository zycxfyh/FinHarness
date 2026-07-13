#!/usr/bin/env python3
"""Serve the persistent local cockpit in explicit read-only or review mode."""

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from finharness.api.app import create_app
from finharness.api.dependencies import DEFAULT_STATE_CORE_RECEIPT_ROOT
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.store import (
    DEFAULT_STATE_CORE_DB_PATH,
    init_state_core,
    open_state_core,
)

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("read-only", "review"), default="read-only")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_CORE_DB_PATH)
    parser.add_argument("--receipt-root", type=Path, default=DEFAULT_STATE_CORE_RECEIPT_ROOT)
    parser.add_argument("--operator-id", default="local-human")
    return parser


def build_app(args: argparse.Namespace):
    if args.host not in _LOOPBACK_HOSTS:
        raise SystemExit("local cockpit may only bind to a loopback host")
    if args.mode == "review":
        engine = init_state_core(args.state_db)
        operator = LocalOperatorContext(args.operator_id)
    else:
        engine = open_state_core(args.state_db)
        operator = None
    return create_app(
        state_core_engine=engine,
        receipt_root=str(args.receipt_root),
        local_operator_context=operator,
    )


def main() -> None:
    args = _parser().parse_args()
    app = build_app(args)
    mode = "governed human review writes" if args.mode == "review" else "read-only"
    print(
        f"FinHarness local cockpit: {mode}; http://{args.host}:{args.port}/cockpit/; "
        "execution remains disabled",
        flush=True,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
