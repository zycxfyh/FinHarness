"""Scan the exposure map and record capital-allocation candidates as governed proposals.

Read-only: candidates carry no execution authority and surface through the existing
``/proposals`` review path. Idempotent per as-of date and detector kind.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.allocation import record_allocation_candidates
from finharness.statecore.store import init_state_core, state_core_db_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record capital-allocation candidates as governed proposals (read-only)."
    )
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--receipt-root", type=Path, default=None)
    args = parser.parse_args()
    engine = init_state_core(state_core_db_path(args.db_path))
    try:
        if args.receipt_root is None:
            report, writes = record_allocation_candidates(engine)
        else:
            report, writes = record_allocation_candidates(engine, receipt_root=args.receipt_root)
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "ok": True,
                "as_of_date": report.as_of_date,
                "candidate_count": len(writes),
                "candidates": [
                    {
                        "kind": write.proposal.kind,
                        "proposal_id": write.proposal.proposal_id,
                        "claim": write.proposal.claim,
                        "receipt_ref": write.receipt_ref,
                    }
                    for write in writes
                ],
                "execution_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
