#!/usr/bin/env python3
"""Read-only closed JSON probe for the #390 stale-version browser acceptance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlmodel import Session, select

from finharness.statecore.models import ReceiptIndex, ReviewEvent
from finharness.statecore.proposal_version import resolve_current_proposal_version
from finharness.statecore.store import open_state_core


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-core-db", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--marker", required=True)
    args = parser.parse_args()

    engine = open_state_core(args.state_core_db)
    try:
        current = resolve_current_proposal_version(
            args.proposal_id,
            engine=engine,
            receipt_root=args.receipt_root,
        )
        with Session(engine) as session:
            events = list(
                session.exec(
                    select(ReviewEvent).where(
                        ReviewEvent.proposal_id == args.proposal_id,
                        ReviewEvent.reason == args.marker,
                    )
                ).all()
            )
            event_indexes = list(
                session.exec(
                    select(ReceiptIndex).where(
                        ReceiptIndex.kind == "state_core_review_event",
                    )
                ).all()
            )
    finally:
        engine.dispose()

    event_ids = {event.review_event_id for event in events}
    receipts = []
    for receipt_path in sorted(
        (args.receipt_root / "review-events").glob("*.json")
    ):
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        event = payload.get("review_event")
        if isinstance(event, dict) and event.get("review_event_id") in event_ids:
            receipts.append(payload)

    print(
        json.dumps(
            {
                "schema": "finharness.browser_stale_proposal_version_probe.v1",
                "proposal_id": args.proposal_id,
                "current_version": {
                    "proposal_version_id": current.proposal_version_id,
                    "receipt_ref": current.receipt_ref,
                },
                "matching_review_event_count": len(events),
                "matching_review_receipt_count": len(receipts),
                "matching_review_index_count": sum(
                    index.receipt_id == f"receipt_{event_id}"
                    for index in event_indexes
                    for event_id in event_ids
                ),
                "bound_versions": [
                    {
                        "proposal_version_id": event.bound_proposal_version_id,
                        "receipt_ref": event.bound_proposal_receipt_ref,
                    }
                    for event in events
                ],
                "execution_allowed": [
                    event.execution_allowed for event in events
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
