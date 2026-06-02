"""Run the first-layer market data LangGraph workflow."""

from __future__ import annotations

import argparse
import json

from finharness.market_data_graph import run_market_data_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-06-30")
    parser.add_argument("--no-catalog", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_market_data_graph(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        write_catalog=not args.no_catalog,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("receipt_ref") else 1


if __name__ == "__main__":
    raise SystemExit(main())
