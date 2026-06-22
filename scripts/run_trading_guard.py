"""Evaluate the behavioral trading guard against persisted trading-state.

Replaces the legacy `cargo run -p finharness-cli -- guard ...` demo. By default
it reads the real persisted state (data/state/trading-state.json) so the guard
reflects actual drawdown/loss history rather than hand-fed flags. Flags can
override for what-if checks.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from finharness.effective_rules import resolve_guard_thresholds
from finharness.trading_guard import TradingState, evaluate_trading_state
from finharness.trading_state_store import load_trading_state


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Behavioral trading guard")
    parser.add_argument("--drawdown-pct", type=float, default=None)
    parser.add_argument("--consecutive-losses", type=int, default=None)
    parser.add_argument("--minutes-since-last-trade", type=int, default=None)
    parser.add_argument("--thesis", action="store_true", help="assert a written thesis exists")
    ns = parser.parse_args(argv)

    record = load_trading_state()
    state = TradingState(
        drawdown_pct=ns.drawdown_pct if ns.drawdown_pct is not None else record.drawdown_pct,
        consecutive_losses=(
            ns.consecutive_losses
            if ns.consecutive_losses is not None
            else record.consecutive_losses
        ),
        minutes_since_last_trade=ns.minutes_since_last_trade,
        planned_trade_has_written_thesis=ns.thesis,
    )
    thresholds, provenance, ignored = resolve_guard_thresholds()
    decision = evaluate_trading_state(state, thresholds)
    print(
        json.dumps(
            {
                "drawdown_pct": state.drawdown_pct,
                "consecutive_losses": state.consecutive_losses,
                "behavior_reset_required": record.behavior_reset_required,
                "effective_thresholds": asdict(thresholds),
                "threshold_provenance": provenance,
                "ignored_rule_changes": ignored,
                "level": decision.level,
                "trade_allowed": decision.trade_allowed,
                "reasons": decision.reasons,
                "required_actions": decision.required_actions,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    # Non-zero when trading should stop, so the task is usable as a gate.
    return 0 if decision.trade_allowed and not record.behavior_reset_required else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
