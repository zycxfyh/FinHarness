"""Run the top-level ten-layer FinHarness LangGraph orchestrator."""

from __future__ import annotations

import argparse
import json

from finharness.ten_layer_graph import run_ten_layer_graph


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-06-30")
    parser.add_argument("--universe", default="")
    parser.add_argument("--forms", default="8-K,10-Q,10-K")
    parser.add_argument("--max-records", type=int, default=30)
    parser.add_argument("--max-hypotheses", type=int, default=10)
    parser.add_argument(
        "--run-layers",
        default="1,2,3,4,5,6,7,8,9,10",
        help="Comma-separated layer numbers or names. Supply snapshots in code to reuse layers.",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--paper", action="store_true")
    parser.add_argument("--quantity", type=int, default=1)
    parser.add_argument(
        "--asset-id",
        action="append",
        default=[],
        help="Research asset id to cite in L5-L10 lineage; may be repeated.",
    )
    parser.add_argument(
        "--strategy-spec-id",
        action="append",
        default=[],
        help="StrategySpec id to cite in L5-L10 lineage; may be repeated.",
    )
    parser.add_argument(
        "--method-spec-id",
        action="append",
        default=[],
        help="MathMethodSpec id to cite in L5-L10 lineage; may be repeated.",
    )
    parser.add_argument(
        "--reference-card-id",
        action="append",
        default=[],
        help="ReferenceCard id to cite in L5-L10 lineage; may be repeated.",
    )
    parser.add_argument(
        "--fake-fill-mode",
        choices=["accepted", "partial", "filled", "reject"],
        default="accepted",
    )
    return parser.parse_args()


def _split_csv(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def _split_layers(value: str) -> list[int | str]:
    layers: list[int | str] = []
    for item in value.split(","):
        text = item.strip()
        if not text:
            continue
        layers.append(int(text) if text.isdigit() else text)
    return layers


def main() -> int:
    args = parse_args()
    mode = "paper" if args.paper else "dry_run"
    result = run_ten_layer_graph(
        symbol=args.symbol,
        start=args.start,
        end=args.end,
        universe=_split_csv(args.universe) or None,
        forms=_split_csv(args.forms),
        max_records=args.max_records,
        max_hypotheses=args.max_hypotheses,
        run_layers=_split_layers(args.run_layers),
        execution_context={
            "requested_mode": mode,
            "operator_execute": args.execute,
            "requested_quantity": args.quantity,
        },
        fake_fill_mode=args.fake_fill_mode,
        research_asset_ids=args.asset_id,
        strategy_spec_ids=args.strategy_spec_id,
        method_spec_ids=args.method_spec_id,
        reference_card_ids=args.reference_card_id,
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("terminal_layer") else 1


if __name__ == "__main__":
    raise SystemExit(main())
