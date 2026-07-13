"""Plan or explicitly apply conservative backup retention."""

from __future__ import annotations

import argparse
import json
import sys

from finharness.backup import BackupPolicy, prune_backups
from finharness.config import load_settings


def main(argv: list[str]) -> int:
    settings = load_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-root", default=str(settings.backup_root))
    parser.add_argument("--retention-count", type=int, default=settings.backup_retention_count)
    parser.add_argument("--retention-days", type=int, default=settings.backup_retention_days)
    parser.add_argument("--apply", action="store_true", help="Delete listed candidates")
    ns = parser.parse_args(argv)
    try:
        result = prune_backups(
            ns.backup_root,
            policy=BackupPolicy(
                min_free_bytes=settings.backup_min_free_bytes,
                retention_count=ns.retention_count,
                retention_days=ns.retention_days,
            ),
            dry_run=not ns.apply,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "execution_allowed": False}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
