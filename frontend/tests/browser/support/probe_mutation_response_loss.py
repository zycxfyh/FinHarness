#!/usr/bin/env python3
"""Read-only closed JSON probe for the #385 browser acceptance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlmodel import Session, select

from finharness.identity import load_identity_mutation_receipt
from finharness.statecore.models import ReviewEvent
from finharness.statecore.store import open_state_core


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-core-db", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--marker", required=True)
    parser.add_argument("--identity-receipt-id")
    args = parser.parse_args()

    engine = open_state_core(args.state_core_db)
    try:
        with Session(engine) as session:
            events = list(
                session.exec(
                    select(ReviewEvent).where(
                        ReviewEvent.proposal_id == args.proposal_id,
                        ReviewEvent.reason == args.marker,
                    )
                ).all()
            )
    finally:
        engine.dispose()

    event_ids = {event.review_event_id for event in events}
    domain_receipts: list[dict[str, object]] = []
    domain_dir = args.receipt_root / "review-events"
    for receipt_path in sorted(domain_dir.glob("*.json")):
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        review_event = payload.get("review_event")
        if (
            isinstance(review_event, dict)
            and review_event.get("review_event_id") in event_ids
        ):
            domain_receipts.append(payload)

    identity_dir = args.receipt_root / "identity"
    identity_paths = sorted(identity_dir.glob("*.json"))
    selected_path = None
    if args.identity_receipt_id:
        selected_path = identity_dir / f"{args.identity_receipt_id}.json"
    elif len(identity_paths) == 1:
        selected_path = identity_paths[0]

    identity = (
        load_identity_mutation_receipt(selected_path)
        if selected_path is not None and selected_path.exists()
        else None
    )
    mutation_ref = (
        f"identity-mutation:{identity['receipt_id']}"
        if identity is not None
        else None
    )

    print(
        json.dumps(
            {
                "schema": "finharness.browser_mutation_response_loss_probe.v1",
                "proposal_id": args.proposal_id,
                "domain_effect_count": len(events),
                "domain_receipt_count": len(domain_receipts),
                "identity_receipt_count": len(identity_paths),
                "identity_receipt_id": (
                    identity.get("receipt_id") if identity is not None else None
                ),
                "identity_state": (
                    identity.get("state") if identity is not None else None
                ),
                "identity_execution_allowed": (
                    identity.get("execution_allowed")
                    if identity is not None
                    else None
                ),
                "resolver_id": (
                    identity.get("reconciliation", {}).get("resolver_id")
                    if identity is not None
                    else None
                ),
                "bound_effect_count": (
                    sum(
                        mutation_ref in event.source_refs
                        for event in events
                    )
                    if mutation_ref is not None
                    else 0
                ),
                "domain_execution_allowed": [
                    event.execution_allowed for event in events
                ],
                "domain_receipt_execution_allowed": [
                    receipt.get("governance", {}).get("execution_allowed")
                    for receipt in domain_receipts
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
