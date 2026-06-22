"""Build the FinHarness market cockpit for a watchlist."""

from __future__ import annotations

import argparse
import json

from finharness.market_cockpit import build_market_cockpit, write_market_cockpit_outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default="SPY,QQQ,NVDA")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-06-13")
    parser.add_argument("--fast", type=int, default=20)
    parser.add_argument("--slow", type=int, default=50)
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Print the cockpit without writing latest JSON/Markdown outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cockpit = build_market_cockpit(
        symbols=args.symbols,
        start=args.start,
        end=args.end,
        ma_fast=args.fast,
        ma_slow=args.slow,
    )
    outputs = {} if args.no_write else write_market_cockpit_outputs(cockpit)
    print(json.dumps({**cockpit, "outputs": outputs}, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
