"""Run the FinHarness governance dashboard graph."""

from __future__ import annotations

import argparse
import json

from finharness.governance_dashboard_graph import run_governance_dashboard_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-checks",
        action="store_true",
        help="Run authoritative release preflight checks before writing the dashboard.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_governance_dashboard_graph(run_checks=args.run_checks)
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
