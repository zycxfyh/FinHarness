"""Run the second-layer indicator LangGraph workflow."""

from __future__ import annotations

import argparse
import json

from finharness.indicator_graph import run_indicator_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-06-30")
    parser.add_argument("--fast", type=int, default=20)
    parser.add_argument("--slow", type=int, default=50)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_indicator_graph(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        ma_fast=args.fast,
        ma_slow=args.slow,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("receipt_ref") else 1


if __name__ == "__main__":
    raise SystemExit(main())
