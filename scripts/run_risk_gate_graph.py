"""Run eighth-layer risk gate LangGraph workflow.

Attestation is fail-closed: without --attest-human-review (plus a reason) or
--interactive (answering the pause prompt), decisions stay needs_human_review.
"""

from __future__ import annotations

import argparse
import json
from uuid import uuid4

from finharness.risk_gate_graph import (
    build_risk_gate_graph,
    resume_risk_gate_graph,
    run_risk_gate_graph,
    run_risk_gate_graph_interactive,
)


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
    parser.add_argument(
        "--attest-human-review",
        action="store_true",
        help="Declare that a human reviewed the candidates (requires --attest-reason).",
    )
    parser.add_argument("--attest-reason", default="")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Pause at the human gate and ask for attestation on stdin.",
    )
    parser.add_argument("--requested-notional", type=float, default=100.0)
    parser.add_argument("--max-paper-notional", type=float, default=1000.0)
    return parser.parse_args()


def _split_csv(value: str) -> list[str]:
    return [item.strip().upper() for item in value.split(",") if item.strip()]


def main() -> int:
    args = parse_args()
    if args.attest_human_review and not args.attest_reason.strip():
        print("--attest-human-review requires --attest-reason")
        return 1
    risk_context = {
        "requested_execution_mode": "live" if args.live_requested else "paper",
        "human_review_attested": args.attest_human_review,
        "requested_notional": args.requested_notional,
        "max_paper_notional": args.max_paper_notional,
    }
    common = {
        "universe": _split_csv(args.universe),
        "forms": _split_csv(args.forms),
        "max_records": args.max_records,
        "max_hypotheses": args.max_hypotheses,
        "symbols": _split_csv(args.symbols),
        "risk_context": risk_context,
        "llm_enabled": args.llm_enabled,
        "hermes_root": args.hermes_root,
    }
    if not args.interactive:
        result = run_risk_gate_graph(**common)
        print(json.dumps(result["final"], ensure_ascii=False, indent=2))
        return 0 if result["final"].get("quality_ok") else 1

    graph = build_risk_gate_graph(interactive=True)
    thread_id = f"cli-{uuid4().hex[:8]}"
    payload = {**common, "research_asset_context": {}}
    result = run_risk_gate_graph_interactive(
        payload=payload, thread_id=thread_id, graph=graph
    )
    if "__interrupt__" in result:
        pending = result["__interrupt__"][0].value
        print(json.dumps(pending, ensure_ascii=False, indent=2))
        answer = input("Attest human review? [y/N]: ").strip().lower()
        reason = ""
        if answer == "y":
            reason = input("Reason (required): ").strip()
        result = resume_risk_gate_graph(
            graph=graph,
            thread_id=thread_id,
            attest=answer == "y" and bool(reason),
            reason=reason,
        )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
    return 0 if result["final"].get("quality_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
