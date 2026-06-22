"""Compute and archive an annual (period) decision retrospective as a dated receipt.

Read-only: it synthesizes existing proposals/attestations/revisions/lessons/rule
changes. It carries no execution authority and changes no rule.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.annual_review import record_annual_review
from finharness.statecore.store import init_state_core, state_core_db_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record an annual decision retrospective (read-only)."
    )
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--receipt-root", type=Path, default=None)
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Calendar year to review; default is a rolling 12 months ending today.",
    )
    args = parser.parse_args()
    engine = init_state_core(state_core_db_path(args.db_path))
    try:
        if args.receipt_root is None:
            review, receipt_ref = record_annual_review(engine, year=args.year)
        else:
            review, receipt_ref = record_annual_review(
                engine, receipt_root=args.receipt_root, year=args.year
            )
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "ok": True,
                "period_label": review.period_label,
                "period_start": review.period_start,
                "period_end": review.period_end,
                "candidate_count": review.candidate_count,
                "open_count": review.open_count,
                "attested_count": review.attested_count,
                "lessons_total": review.lessons_total,
                "lessons_closed": review.lessons_closed,
                "lessons_open": list(review.lessons_open),
                "receipt_ref": receipt_ref,
                "execution_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
