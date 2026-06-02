"""Run the daily first-four-layer evidence LangGraph workflow."""

from __future__ import annotations

import argparse
import json

from finharness.daily_evidence_graph import run_daily_evidence_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-06-30")
    parser.add_argument("--universe", default="AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,SPY,QQQ")
    parser.add_argument("--market-symbols", default="SPY,QQQ")
    parser.add_argument("--forms", default="8-K,10-Q,10-K")
    parser.add_argument("--per-symbol-limit", type=int, default=40)
    parser.add_argument("--max-records", type=int, default=30)
    parser.add_argument("--fast", type=int, default=20)
    parser.add_argument("--slow", type=int, default=50)
    return parser.parse_args()


def split_csv(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def main() -> int:
    args = parse_args()
    result = run_daily_evidence_graph(
        universe=split_csv(args.universe),
        market_symbols=split_csv(args.market_symbols),
        start=args.start,
        end=args.end,
        forms=split_csv(args.forms),
        per_symbol_limit=args.per_symbol_limit,
        max_records=args.max_records,
        ma_fast=args.fast,
        ma_slow=args.slow,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("receipt_ref") else 1


if __name__ == "__main__":
    raise SystemExit(main())
