"""Run the FinHarness quality governance graph."""

from __future__ import annotations

import argparse
import json

from finharness.quality_governance_graph import run_quality_governance_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-checks",
        action="store_true",
        help="Run authoritative Taskfile checks instead of recording not_run placeholders.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_quality_governance_graph(run_checks=args.run_checks)
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if not result["final"]["release_decision"]["release_blocked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
