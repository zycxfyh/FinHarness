#!/usr/bin/env python3
"""Test-only server for the real-browser stale ProposalVersion acceptance."""

from __future__ import annotations

import json
import os
from pathlib import Path

import uvicorn

from finharness.api.app import create_app
from finharness.identity import (
    OperatorContext,
    PrincipalIdentity,
    TestIdentityProvider,
)
from finharness.statecore.proposal_version import resolve_current_proposal_version
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core

PROPOSAL_ID = "browser-stale-proposal-version"
METADATA_SCHEMA = "finharness.browser_stale_proposal_version_fixture.v1"


def _identity() -> OperatorContext:
    return OperatorContext(
        principal=PrincipalIdentity(
            principal_id="principal:alice",
            provider_id="browser-stale-version-provider",
            principal_kind="human",
        ),
        authentication_method="test_bearer",
        authenticated_at_utc="2026-07-18T00:00:00+00:00",
        authentication_epoch_id="alice-stale-version-session",
        authentication_expires_at_utc="2099-01-01T00:00:00+00:00",
    )


def main() -> None:
    root = Path(os.environ["BROWSER_STALE_PROPOSAL_VERSION_ROOT"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    state_db = root / "state.sqlite"
    receipt_root = root / "receipts"
    engine = init_state_core(state_db)

    create_governed_proposal(
        proposal_id=PROPOSAL_ID,
        kind="browser_stale_proposal_version_fixture",
        claim="A governed write must bind the exact ProposalVersion shown to the operator.",
        evidence={"synthetic": True, "external_network": False},
        source_refs=["fixture://browser-stale-proposal-version"],
        decision_scaffold={
            "decision_intent": "Reject a stale-tab governed write without side effects",
            "thesis": "The immutable ProposalVersion pair owns basis consistency",
            "do_nothing_case": "Reload the stale tab before writing",
            "risk_if_wrong": "A review event is admitted against unseen state",
        },
        engine=engine,
        receipt_root=receipt_root,
    )
    initial = resolve_current_proposal_version(
        PROPOSAL_ID,
        engine=engine,
        receipt_root=receipt_root,
    )

    provider = TestIdentityProvider({"alice-session": _identity()})
    app = create_app(
        state_core_engine=engine,
        receipt_root=str(receipt_root),
        identity_provider=provider,
    )
    capability = app.state.keyed_mutation_route_capabilities.by_route(
        "POST",
        "/proposals/{proposal_id}/review-events",
    )
    if capability is None:
        raise RuntimeError("review-event keyed-mutation capability is missing")

    metadata = {
        "schema": METADATA_SCHEMA,
        "state_db": str(state_db),
        "receipt_root": str(receipt_root),
        "proposal_id": PROPOSAL_ID,
        "initial_version": {
            "proposal_version_id": initial.proposal_version_id,
            "receipt_ref": initial.receipt_ref,
        },
        "review_event_path": f"/proposals/{PROPOSAL_ID}/review-events",
        "scaffold_path": f"/proposals/{PROPOSAL_ID}/decision-scaffold",
        "capability_id": capability.capability_id,
        "execution_allowed": capability.execution_allowed,
    }
    (root / "fixture.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("BROWSER_STALE_PROPOSAL_VERSION_PORT", "8792")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
