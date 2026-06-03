"""Run the FinHarness release preflight graph."""

from __future__ import annotations

import argparse
import json

from finharness.release_preflight_graph import run_release_preflight_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-checks",
        action="store_true",
        help="Run authoritative local checks before sealing the release receipt.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_release_preflight_graph(run_checks=args.run_checks)
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"]["release_gate"]["release_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
