"""Place a live OKX order through the fail-closed gate, with attestation.

This is the only sanctioned live-mutation entry. Every order passes through
finharness.okx_live_gate, which enforces the behavioral guard against persisted
trading-state, a notional cap, attestation, and a receipt (red-team F1/F3/F4/
F5/F7). Authorization is an interactive out-of-band confirmation that echoes the
exact order (F2 v1); the env gate FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1 still
applies inside the gate.

Usage:

    uv run python scripts/okx_live_order.py <module> <action> [okx args...] \
        --attester "<name>" --reason "<written-plan ref>" --thesis \
        [--max-notional N] [--dry-run] [--yes]

--max-notional is a per-request tightening limit. It cannot raise the governed
ceiling resolved by finharness.okx_live_gate.
--dry-run assesses and prints the decision without touching the broker.
--yes skips the interactive prompt (discouraged; for non-interactive contexts).
"""

from __future__ import annotations

import argparse
import json
import sys

from finharness.okx_cli import OkxCliError
from finharness.okx_live_gate import (
    DEFAULT_MAX_LIVE_NOTIONAL,
    LiveOrderBlocked,
    LiveOrderRequest,
    assess_live_order,
    execute_live_order,
    order_notional,
)


def _parse(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(description="Gated live OKX order")
    parser.add_argument("module")
    parser.add_argument("action")
    parser.add_argument("--attester", required=True, help="who authorizes this order")
    parser.add_argument("--reason", required=True, help="written plan reference / reason")
    parser.add_argument(
        "--thesis",
        action="store_true",
        help="assert a written thesis (entry/invalidation/size/max-loss) exists",
    )
    parser.add_argument(
        "--max-notional",
        type=float,
        default=DEFAULT_MAX_LIVE_NOTIONAL,
        help="per-request notional limit; can only tighten the governed ceiling",
    )
    parser.add_argument("--minutes-since-last-trade", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    return parser.parse_known_args(argv)


def _build_request(ns: argparse.Namespace, order_args: list[str]) -> LiveOrderRequest:
    return LiveOrderRequest(
        module=ns.module,
        action=ns.action,
        args=order_args,
        attester=ns.attester,
        reason=ns.reason,
        has_written_thesis=ns.thesis,
        request_limit=ns.max_notional,
        minutes_since_last_trade=ns.minutes_since_last_trade,
    )


def _print_decision(request: LiveOrderRequest, decision) -> None:
    print(
        json.dumps(
            {
                "module": request.module,
                "action": request.action,
                "args": request.args,
                "attester": request.attester,
                "reason": request.reason,
                "notional": decision.notional,
                "request_limit": decision.request_limit,
                "configured_ceiling": decision.configured_ceiling,
                "effective_ceiling": decision.effective_ceiling,
                "enforced_cap": decision.enforced_cap,
                "request_limit_clamped_to_ceiling": (
                    decision.request_limit_clamped_to_ceiling
                ),
                "guard_level": decision.guard_level,
                "allowed": decision.allowed,
                "blocking_reasons": decision.blocking_reasons,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _confirm_interactively(request: LiveOrderRequest) -> bool:
    phrase = f"CONFIRM {request.action} {request.module}"
    command = f"okx --live {request.module} {request.action} {' '.join(request.args)}"
    decision = assess_live_order(request)
    print("\n=== LIVE ORDER CONFIRMATION ===", file=sys.stderr)
    print(f"  {command}", file=sys.stderr)
    print(f"  request limit: {request.request_limit}", file=sys.stderr)
    print(f"  enforced cap: {decision.enforced_cap}", file=sys.stderr)
    print(f"  attester: {request.attester} | reason: {request.reason}", file=sys.stderr)
    print(f'Type exactly "{phrase}" to place this live order: ', end="", file=sys.stderr)
    try:
        typed = input().strip()
    except EOFError:
        return False
    return typed == phrase


def main(argv: list[str]) -> int:
    ns, order_args = _parse(argv)
    request = _build_request(ns, order_args)

    decision = assess_live_order(request)
    _print_decision(request, decision)

    if ns.dry_run:
        return 0 if decision.allowed else 1

    if not decision.allowed:
        print("refused by gate; not placing order", file=sys.stderr)
        return 1

    # F2 v1: out-of-band confirmation echoing the exact order.
    if not ns.yes and not _confirm_interactively(request):
        print("confirmation phrase mismatch; aborting", file=sys.stderr)
        return 1

    if order_notional(request) is None:  # defensive; gate already checks
        print("notional unbounded; aborting", file=sys.stderr)
        return 1

    try:
        result = execute_live_order(request)
    except LiveOrderBlocked as blocked:
        print(json.dumps({"blocked": blocked.decision.blocking_reasons}, ensure_ascii=False))
        return 1
    except OkxCliError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1

    print(json.dumps({"placed": True, "receipt_ref": result["receipt_ref"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
