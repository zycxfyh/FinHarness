"""Run the LangGraph institutional paper trade workflow."""

from __future__ import annotations

import argparse
import json

from finharness.trade_graph import run_institutional_paper_trade


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--qty", default="1")
    parser.add_argument("--universe", default="SPY,QQQ,AAPL,MSFT,NVDA")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    universe = [symbol.strip().upper() for symbol in args.universe.split(",") if symbol.strip()]
    result = run_institutional_paper_trade(
        universe=universe,
        execute=args.execute,
        order_qty=args.qty,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("receipt_path") else 1


if __name__ == "__main__":
    raise SystemExit(main())
