#!/usr/bin/env python3
"""Persistent fixture server for the local-review real-browser gate."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import uvicorn
from sqlmodel import Session, select

from finharness.statecore.models import Proposal
from finharness.statecore.proposals import create_governed_proposal
from serve_local_cockpit import build_app

SCAFFOLD = {
    "decision_intent": "Complete a local human review",
    "thesis": "The synthetic fixture is ready for review",
    "do_nothing_case": "No decision is recorded",
    "risk_if_wrong": "The synthetic conclusion is wrong",
}


def _args() -> argparse.Namespace:
    root = Path(os.environ["LOCAL_REVIEW_SMOKE_ROOT"])
    return argparse.Namespace(
        mode=os.environ.get("LOCAL_REVIEW_SMOKE_MODE", "review"),
        host="127.0.0.1",
        port=int(os.environ.get("LOCAL_REVIEW_SMOKE_PORT", "8774")),
        state_db=root / "state.sqlite",
        receipt_root=root / "receipts",
        operator_id="browser-test-human",
    )


def _seed(app, receipt_root: Path) -> None:
    with Session(app.state.state_core_engine) as session:
        existing = set(session.exec(select(Proposal.proposal_id)).all())
    for proposal_id, claim in (
        ("browser-confirm", "Browser confirm fixture"),
        ("browser-reject", "Browser reject fixture"),
        ("browser-defer", "Browser defer fixture"),
    ):
        if proposal_id in existing:
            continue
        create_governed_proposal(
            proposal_id=proposal_id,
            kind="local_review_fixture",
            claim=claim,
            evidence={"synthetic": True},
            source_refs=["fixture://local-review-browser"],
            decision_scaffold=SCAFFOLD,
            engine=app.state.state_core_engine,
            receipt_root=receipt_root,
        )


def main() -> None:
    args = _args()
    app = build_app(args)
    if args.mode == "review":
        _seed(app, args.receipt_root)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
