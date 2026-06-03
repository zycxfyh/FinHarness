"""Run eighth-layer risk gate LangGraph workflow."""

from __future__ import annotations

import argparse
import json

from finharness.risk_gate_graph import run_risk_gate_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,SPY,QQQ")
    parser.add_argument("--forms", default="8-K,10-Q,10-K")
    parser.add_argument("--max-records", type=int, default=30)
    parser.add_argument("--max-hypotheses", type=int, default=10)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--llm-enabled", action="store_true")
    parser.add_argument("--hermes-root", default="/root/projects/hermes-agent")
    parser.add_argument("--live-requested", action="store_true")
    parser.add_argument("--human-review-missing", action="store_true")
    parser.add_argument("--requested-notional", type=float, default=100.0)
    parser.add_argument("--max-paper-notional", type=float, default=1000.0)
    return parser.parse_args()


def _split_csv(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def main() -> int:
    args = parse_args()
    risk_context = {
        "requested_execution_mode": "live" if args.live_requested else "paper",
        "human_review_attested": not args.human_review_missing,
        "requested_notional": args.requested_notional,
        "max_paper_notional": args.max_paper_notional,
    }
    result = run_risk_gate_graph(
        universe=_split_csv(args.universe),
        forms=_split_csv(args.forms),
        max_records=args.max_records,
        max_hypotheses=args.max_hypotheses,
        symbols=_split_csv(args.symbols),
        risk_context=risk_context,
        llm_enabled=args.llm_enabled,
        hermes_root=args.hermes_root,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("quality_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
