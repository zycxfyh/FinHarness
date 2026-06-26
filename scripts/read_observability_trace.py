"""Read a local observability trace-index receipt as a bounded summary.

Trace ids are correlation handles only. This script reads the
``observability_trace_index`` receipt and checks whether referenced receipt files
exist; it does not print raw domain receipt payloads.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.observability import (
    DEFAULT_OBSERVABILITY_RECEIPT_ROOT,
    summarize_trace_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace_id", help="FinHarness trace id, e.g. trace_abc123")
    parser.add_argument(
        "--receipt-root",
        type=Path,
        default=DEFAULT_OBSERVABILITY_RECEIPT_ROOT,
        help="Observability receipt root (default: data/receipts/observability).",
    )
    args = parser.parse_args()

    summary = summarize_trace_receipt(args.trace_id, receipt_root=args.receipt_root)
    print(json.dumps(summary.to_json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
