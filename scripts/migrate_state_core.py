"""Apply state-core schema migrations (PRAGMA user_version) to an existing database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import text

from finharness.statecore.store import (
    StateCoreStoreError,
    migrate_state_core,
    open_state_core,
    state_core_db_path,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply state-core PRAGMA user_version migrations."
    )
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args()
    engine = open_state_core(state_core_db_path(args.db_path))
    try:
        migrate_state_core(engine)
        with engine.connect() as connection:
            version = int(connection.execute(text("PRAGMA user_version")).scalar_one())
    except StateCoreStoreError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "execution_allowed": False}, indent=2))
        return 1
    finally:
        engine.dispose()
    print(json.dumps({"ok": True, "user_version": version, "execution_allowed": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
