"""Run ninth-layer execution LangGraph workflow."""

from __future__ import annotations

import argparse
import json

from finharness.execution_graph import run_execution_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--universe", default="AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,SPY,QQQ")
    parser.add_argument("--forms", default="8-K,10-Q,10-K")
    parser.add_argument("--max-records", type=int, default=30)
    parser.add_argument("--max-hypotheses", type=int, default=10)
    parser.add_argument("--symbols", default="")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--paper", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--attest-human-review",
        action="store_true",
        help="Fail-closed: without this flag the run cannot create order requests.",
    )
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument("--max-quantity", type=int, default=10)
    parser.add_argument("--reference-price", type=float, default=100.0)
    parser.add_argument(
        "--fake-fill-mode",
        choices=["accepted", "partial", "filled", "reject"],
        default="accepted",
    )
    parser.add_argument("--cancel-after-submit", action="store_true")
    return parser.parse_args()


def _split_csv(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def main() -> int:
    args = parse_args()
    mode = "live" if args.live else "paper" if args.paper else "dry_run"
    execution_context = {
        "requested_mode": mode,
        "operator_execute": args.execute,
        "human_review_attested": args.attest_human_review,
        "requested_quantity": args.quantity,
        "max_order_quantity": args.max_quantity,
        "reference_price": args.reference_price,
        "cancel_after_submit": args.cancel_after_submit,
    }
    result = run_execution_graph(
        universe=_split_csv(args.universe),
        forms=_split_csv(args.forms),
        max_records=args.max_records,
        max_hypotheses=args.max_hypotheses,
        symbols=_split_csv(args.symbols),
        execution_context=execution_context,
        fake_fill_mode=args.fake_fill_mode,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("quality_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
