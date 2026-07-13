"""Audit or safely recover the capital-import receipt/database mirror."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.capital_import_recovery import (
    audit_capital_imports,
    recover_capital_imports,
)
from finharness.statecore.store import init_state_core, state_core_db_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply deterministic repairs and emit a recovery receipt.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = init_state_core(state_core_db_path(args.db_path))
    try:
        if args.apply:
            recovery = recover_capital_imports(
                engine=engine,
                receipt_root=args.receipt_root,
            )
            payload = recovery.model_dump(mode="json", by_alias=True)
            ok = recovery.after.ok
        else:
            audit = audit_capital_imports(
                engine=engine,
                receipt_root=args.receipt_root,
            )
            payload = audit.model_dump(mode="json", by_alias=True)
            ok = audit.ok
    finally:
        engine.dispose()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
