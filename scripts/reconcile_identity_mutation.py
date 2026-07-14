"""Inspect or reconcile a pending API mutation from domain truth."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from finharness.api.routes_proposals import (
    reconcile_proposal_create_identity_mutation,
)
from finharness.identity import (
    IdentityMutationError,
    load_identity_mutation_receipt,
)
from finharness.statecore.store import (
    open_state_core,
    state_core_db_path,
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--reconciled-by")
    parser.add_argument("--reason")
    parser.add_argument(
        "--state-core-db",
        type=Path,
        default=state_core_db_path(),
    )
    parser.add_argument(
        "--receipt-root",
        type=Path,
        help=("StateCore receipt root. Defaults to the parent of the identity receipt directory."),
    )
    args = parser.parse_args(argv)

    try:
        current = load_identity_mutation_receipt(args.receipt)
        request_binding = current.get("request", {})
        resolver = (
            "finharness.api.proposal_create.v1"
            if request_binding.get("method") == "POST"
            and request_binding.get("path") == "/proposals"
            else None
        )

        if not args.apply:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "dry_run": True,
                        "receipt_id": current.get("receipt_id"),
                        "state": current.get("state"),
                        "request": request_binding,
                        "resolver": resolver,
                        "execution_allowed": False,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if not args.reconciled_by or not args.reason:
            parser.error("--apply requires --reconciled-by and --reason")
        if resolver is None:
            raise IdentityMutationError("no typed reconciliation resolver for this mutation route")

        receipt_root = (
            args.receipt_root if args.receipt_root is not None else args.receipt.parent.parent
        )
        engine = open_state_core(args.state_core_db)
        try:
            result = reconcile_proposal_create_identity_mutation(
                args.receipt,
                engine=engine,
                receipt_root=receipt_root,
                reconciled_by=args.reconciled_by,
                reason=args.reason,
            )
        finally:
            engine.dispose()

    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "execution_allowed": False,
                }
            )
        )
        return 1

    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": False,
                "receipt_id": result["receipt_id"],
                "state": result["state"],
                "reconciliation": result["reconciliation"],
                "execution_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
