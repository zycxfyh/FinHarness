"""Inspect or explicitly reconcile a pending API mutation identity receipt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finharness.identity import reconcile_identity_mutation_as_applied


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reconciled-by")
    parser.add_argument("--reason")
    parser.add_argument("--status-code", type=int, default=200)
    parser.add_argument("--response-file", type=Path)
    parser.add_argument("--content-type", default="application/json")
    args = parser.parse_args(argv)
    try:
        current = json.loads(args.receipt.read_text(encoding="utf-8"))
        if not args.apply:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "dry_run": True,
                        "receipt_id": current.get("receipt_id"),
                        "state": current.get("state"),
                        "request": current.get("request"),
                        "execution_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if not args.reconciled_by or not args.reason or args.response_file is None:
            parser.error("--apply requires --reconciled-by, --reason, and --response-file")
        result = reconcile_identity_mutation_as_applied(
            args.receipt,
            reconciled_by=args.reconciled_by,
            reason=args.reason,
            status_code=args.status_code,
            response_body=args.response_file.read_bytes(),
            content_type=args.content_type,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "execution_allowed": False}))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": False,
                "receipt_id": result["receipt_id"],
                "state": result["state"],
                "execution_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
