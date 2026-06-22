"""Import a real Beancount ledger into the state core via bean-query."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.beancount_adapter import (
    BeancountLedgerError,
    ingest_beancount_ledger,
    result_json,
)
from finharness.statecore.store import init_state_core, state_core_db_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mirror a Beancount ledger's holdings and liabilities into state core."
    )
    parser.add_argument("ledger_path", type=Path)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--receipt-root", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = init_state_core(state_core_db_path(args.db_path))
    try:
        if args.receipt_root is None:
            result = ingest_beancount_ledger(args.ledger_path, engine=engine)
        else:
            result = ingest_beancount_ledger(
                args.ledger_path,
                engine=engine,
                receipt_root=args.receipt_root,
            )
    except BeancountLedgerError as exc:
        print(result_json_error(str(exc)))
        return 1
    finally:
        engine.dispose()
    print(result_json(result))
    return 0


def result_json_error(error: str) -> str:
    return json.dumps(
        {
            "ok": False,
            "error": error,
            "execution_allowed": False,
        },
        ensure_ascii=False,
        indent=2,
    )


if __name__ == "__main__":
    raise SystemExit(main())
