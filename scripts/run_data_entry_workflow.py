from __future__ import annotations

import argparse

from finharness.finance_graph import run_finance_graph


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the top-wheel data entry workflow.")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-06-30")
    parser.add_argument("--fast", type=int, default=20)
    parser.add_argument("--slow", type=int, default=50)
    args = parser.parse_args()

    result = run_finance_graph(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        fast=args.fast,
        slow=args.slow,
    )
    summary = result["workflow"]

    print(f"symbol={args.symbol}")
    print(f"history_rows={summary['history_rows']}")
    print(f"history_path={summary['history_path']}")
    print(f"risk_note_path={summary['risk_note_path']}")
    print(f"backtest_return={summary['backtest']['total_return']:.2%}")
    print(f"risk_eval_ok={result['eval']['ok']}")
    print("data_source=OpenBB:yfinance quote + yfinance/Yahoo Finance history; not TradingView/TV")


if __name__ == "__main__":
    main()
