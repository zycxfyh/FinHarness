from __future__ import annotations

import argparse
import sys

from finharness.agent_tools import describe_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Describe FinHarness Agent tools.")
    parser.add_argument("--profile", default="default")
    args = parser.parse_args()
    try:
        print(describe_agent(profile_name=args.profile))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
