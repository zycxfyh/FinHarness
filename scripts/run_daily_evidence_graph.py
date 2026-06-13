"""Run the daily first-four-layer evidence LangGraph workflow.

Loop 1 (observation loop) entrypoint. By default the run is driven by a
watchlist file and a rolling date window ending today, so a scheduler can
invoke it unchanged every day.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from finharness.daily_evidence_graph import run_daily_evidence_graph

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WATCHLIST = ROOT / "data" / "watchlists" / "equity-core.json"
DEFAULT_LOOKBACK_DAYS = 180


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--watchlist",
        default=str(DEFAULT_WATCHLIST),
        help="Watchlist JSON with universe/market_symbols/forms.",
    )
    parser.add_argument("--start", default=None, help="Default: end minus lookback days.")
    parser.add_argument("--end", default=None, help="Default: today (UTC).")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--universe", default=None, help="CSV override of the watchlist.")
    parser.add_argument("--market-symbols", default=None, help="CSV override.")
    parser.add_argument("--forms", default=None, help="CSV override.")
    parser.add_argument("--per-symbol-limit", type=int, default=40)
    parser.add_argument("--max-records", type=int, default=30)
    parser.add_argument("--fast", type=int, default=20)
    parser.add_argument("--slow", type=int, default=50)
    return parser.parse_args()


def split_csv(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def load_watchlist(path: str) -> dict[str, list[str]]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text(encoding="utf-8"))
    return {
        "universe": [str(item).upper() for item in payload.get("universe", [])],
        "market_symbols": [str(item).upper() for item in payload.get("market_symbols", [])],
        "forms": [str(item) for item in payload.get("forms", [])],
    }


def rolling_window(start: str | None, end: str | None, lookback_days: int) -> tuple[str, str]:
    end_date = (
        datetime.strptime(end, "%Y-%m-%d").date()
        if end
        else datetime.now(UTC).date()
    )
    start_date = (
        datetime.strptime(start, "%Y-%m-%d").date()
        if start
        else end_date - timedelta(days=lookback_days)
    )
    return start_date.isoformat(), end_date.isoformat()


def main() -> int:
    args = parse_args()
    watchlist = load_watchlist(args.watchlist)
    universe = split_csv(args.universe) if args.universe else watchlist.get("universe") or []
    market_symbols = (
        split_csv(args.market_symbols)
        if args.market_symbols
        else watchlist.get("market_symbols") or ["SPY", "QQQ"]
    )
    forms = (
        split_csv(args.forms)
        if args.forms
        else watchlist.get("forms") or ["8-K", "10-Q", "10-K"]
    )
    if not universe:
        print("no universe: provide --universe or a watchlist file with symbols")
        return 1
    start, end = rolling_window(args.start, args.end, args.lookback_days)
    result = run_daily_evidence_graph(
        universe=universe,
        market_symbols=market_symbols,
        start=start,
        end=end,
        forms=forms,
        per_symbol_limit=args.per_symbol_limit,
        max_records=args.max_records,
        ma_fast=args.fast,
        ma_slow=args.slow,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("receipt_ref") else 1


if __name__ == "__main__":
    raise SystemExit(main())
