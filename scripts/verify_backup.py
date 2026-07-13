"""Verify that a backup is complete, bound, and readable for restoration."""

from __future__ import annotations

import argparse
import json
import sys

from finharness.backup import verify_backup


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", help="Backup directory or manifest.json path")
    ns = parser.parse_args(argv)
    try:
        result = verify_backup(ns.backup)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "execution_allowed": False}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
