#!/usr/bin/env python3
"""Test-only server for the real-browser mutation response-loss acceptance."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import uvicorn

import finharness.api.app as api_app
from finharness.api.app import create_app
from finharness.identity import (
    IdentityMutationClaim,
    OperatorContext,
    PrincipalIdentity,
    TestIdentityProvider,
)
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core

PROPOSAL_ID = "browser-response-loss"
PROPOSAL_CLAIM = "Browser response-loss acceptance fixture"
TARGET_PATH = f"/proposals/{PROPOSAL_ID}/review-events"
METADATA_SCHEMA = "finharness.browser_mutation_response_loss_fixture.v1"


def _identity() -> OperatorContext:
    return OperatorContext(
        principal=PrincipalIdentity(
            principal_id="principal:alice",
            provider_id="browser-response-loss-provider",
            principal_kind="human",
        ),
        authentication_method="test_bearer",
        authenticated_at_utc="2026-07-18T00:00:00+00:00",
        authentication_epoch_id="alice-response-loss-session",
        authentication_expires_at_utc="2099-01-01T00:00:00+00:00",
    )


def _write_metadata(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> None:
    root = Path(os.environ["BROWSER_MUTATION_RESPONSE_LOSS_ROOT"]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    state_db = root / "state.sqlite"
    receipt_root = root / "receipts"
    metadata_path = root / "fixture.json"
    engine = init_state_core(state_db)

    create_governed_proposal(
        proposal_id=PROPOSAL_ID,
        kind="browser_response_loss_fixture",
        claim=PROPOSAL_CLAIM,
        evidence={"synthetic": True, "external_network": False},
        source_refs=["fixture://browser-mutation-response-loss"],
        decision_scaffold={
            "decision_intent": "Prove one logical review event survives response loss",
            "thesis": "Typed reconciliation restores the canonical response",
            "do_nothing_case": "The pending mutation remains operator-visible",
            "risk_if_wrong": "A retry creates a duplicate domain effect",
        },
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

    metadata: dict[str, Any] = {
        "schema": METADATA_SCHEMA,
        "state_db": str(state_db),
        "receipt_root": str(receipt_root),
        "proposal_id": PROPOSAL_ID,
        "proposal_claim": PROPOSAL_CLAIM,
        "target_path": TARGET_PATH,
        "capability_id": capability.capability_id,
        "resolver_id": capability.resolver_id,
        "execution_allowed": capability.execution_allowed,
        "terminalization_fault": {
            "owner": "finharness.api.app.complete_identity_mutation",
            "triggered": False,
            "trigger_count": 0,
        },
    }
    _write_metadata(metadata_path, metadata)

    original_complete = api_app.complete_identity_mutation
    fault_lock = threading.Lock()

    def fail_first_target_terminalization(
        claim: IdentityMutationClaim,
        **kwargs: Any,
    ) -> dict[str, Any]:
        request = claim.payload.get("request", {})
        is_target = (
            claim.disposition == "execute"
            and claim.payload.get("state") == "pending"
            and request.get("method") == "POST"
            and request.get("path") == TARGET_PATH
        )
        with fault_lock:
            already_triggered = bool(
                metadata["terminalization_fault"]["triggered"]
            )
            if is_target and not already_triggered:
                metadata["terminalization_fault"] = {
                    "owner": "finharness.api.app.complete_identity_mutation",
                    "triggered": True,
                    "trigger_count": 1,
                }
                _write_metadata(metadata_path, metadata)
                raise RuntimeError(
                    "test-only response-loss fault before identity terminalization"
                )
        return original_complete(claim, **kwargs)

    # Patch the namespace where the middleware looks up the canonical owner.
    # This isolated process has no production trigger or HTTP control surface.
    api_app.complete_identity_mutation = fail_first_target_terminalization

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=int(os.environ.get("BROWSER_MUTATION_RESPONSE_LOSS_PORT", "8791")),
        log_level="warning",
    )


if __name__ == "__main__":
    main()
