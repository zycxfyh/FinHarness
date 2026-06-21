"""Import a read-only personal-finance export into the state core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.personal_finance import (
    PersonalFinanceExportError,
    ingest_personal_finance_export,
    result_json,
)
from finharness.statecore.store import init_state_core, state_core_db_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a Beancount/Fava-style normalized CSV export."
    )
    parser.add_argument("export_path", type=Path)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--receipt-root", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine = init_state_core(state_core_db_path(args.db_path))
    try:
        if args.receipt_root is None:
            result = ingest_personal_finance_export(args.export_path, engine=engine)
        else:
            result = ingest_personal_finance_export(
                args.export_path,
                engine=engine,
                receipt_root=args.receipt_root,
            )
    except PersonalFinanceExportError as exc:
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
