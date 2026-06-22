"""Audit whether FinHarness receipts are consumed by reviews, lessons, or docs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.receipt_usage_audit import (
    ROOT,
    build_receipt_usage_audit,
    write_receipt_usage_audit,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write data/receipts/receipt-usage-audit/latest.json.",
    )
    parser.add_argument("--limit", type=int, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = build_receipt_usage_audit(root=args.root)
    refs = write_receipt_usage_audit(audit, root=args.root) if args.write else {}
    summary = {
        "workflow": audit["workflow"],
        "summary": audit["summary"],
        "sample_unreferenced_receipts": audit["unreferenced_receipts"][: args.limit],
        "sample_missing_references": audit["missing_references"][: args.limit],
        **refs,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
