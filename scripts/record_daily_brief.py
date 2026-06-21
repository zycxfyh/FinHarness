"""Compute and archive today's unified daily brief as a dated receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.daily_brief import record_daily_brief
from finharness.statecore.store import init_state_core, state_core_db_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record the unified daily brief as a dated receipt."
    )
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--receipt-root", type=Path, default=None)
    args = parser.parse_args()
    engine = init_state_core(state_core_db_path(args.db_path))
    try:
        if args.receipt_root is None:
            brief, receipt_ref = record_daily_brief(engine)
        else:
            brief, receipt_ref = record_daily_brief(engine, receipt_root=args.receipt_root)
    finally:
        engine.dispose()
    print(
        json.dumps(
            {
                "ok": True,
                "receipt_ref": receipt_ref,
                "headline": brief.headline,
                "execution_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
