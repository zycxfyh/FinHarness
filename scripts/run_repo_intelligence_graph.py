"""Run the local FinHarness repo intelligence graph."""

from __future__ import annotations

import argparse
import json

from finharness.repo_intelligence_graph import run_repo_intelligence_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--changed-file",
        action="append",
        default=None,
        help="Override changed file detection; may be repeated.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_repo_intelligence_graph(changed_files=args.changed_file)
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
