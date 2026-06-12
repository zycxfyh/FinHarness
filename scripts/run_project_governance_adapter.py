"""Run the FinHarness Project Governance adapter bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.project_governance_adapter import (
    DEFAULT_WORKSTATION_RECEIPT,
    run_finharness_project_governance_adapter,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workstation-receipt",
        default=str(DEFAULT_WORKSTATION_RECEIPT),
        help="Path to workstation-lab's FinHarness project governance receipt.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not write the FinHarness adapter receipt.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_finharness_project_governance_adapter(
        workstation_receipt_path=Path(args.workstation_receipt),
        write_receipt=not args.no_write,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "adapted" else 1


if __name__ == "__main__":
    raise SystemExit(main())
