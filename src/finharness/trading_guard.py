"""Behavioral risk guardrails for trading sessions.

The guard is not a strategy. It is a circuit breaker for moments when losses
and stress make execution quality deteriorate.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuardThresholds:
    hard_stop_drawdown_pct: float = -3.0
    caution_drawdown_pct: float = -1.5
    hard_stop_consecutive_losses: int = 3
    caution_consecutive_losses: int = 2
    min_minutes_between_trades_after_loss: int = 30


@dataclass(frozen=True)
class TradingState:
    drawdown_pct: float
    consecutive_losses: int
    minutes_since_last_trade: int | None = None
    planned_trade_has_written_thesis: bool = False


@dataclass(frozen=True)
class GuardDecision:
    level: str
    trade_allowed: bool
    reasons: list[str]
    required_actions: list[str]


def evaluate_trading_state(
    state: TradingState,
    thresholds: GuardThresholds | None = None,
) -> GuardDecision:
    thresholds = thresholds or GuardThresholds()
    reasons: list[str] = []
    actions: list[str] = []

    hard_stop = False
    caution = False

    if state.drawdown_pct <= thresholds.hard_stop_drawdown_pct:
        hard_stop = True
        reasons.append(
            f"drawdown {state.drawdown_pct:.2f}% breached hard stop "
            f"{thresholds.hard_stop_drawdown_pct:.2f}%"
        )
    elif state.drawdown_pct <= thresholds.caution_drawdown_pct:
        caution = True
        reasons.append(
            f"drawdown {state.drawdown_pct:.2f}% breached caution "
            f"{thresholds.caution_drawdown_pct:.2f}%"
        )

    if state.consecutive_losses >= thresholds.hard_stop_consecutive_losses:
        hard_stop = True
        reasons.append(
            f"{state.consecutive_losses} consecutive losses breached hard stop "
            f"{thresholds.hard_stop_consecutive_losses}"
        )
    elif state.consecutive_losses >= thresholds.caution_consecutive_losses:
        caution = True
        reasons.append(
            f"{state.consecutive_losses} consecutive losses breached caution "
            f"{thresholds.caution_consecutive_losses}"
        )

    if (
        state.minutes_since_last_trade is not None
        and state.consecutive_losses > 0
        and state.minutes_since_last_trade < thresholds.min_minutes_between_trades_after_loss
    ):
        caution = True
        reasons.append(
            f"only {state.minutes_since_last_trade} minutes since a losing trade; "
            f"minimum is {thresholds.min_minutes_between_trades_after_loss}"
        )

    if not state.planned_trade_has_written_thesis:
        caution = True
        reasons.append("planned trade has no written thesis")

    if hard_stop:
        actions.extend(
            [
                "Stop opening new trades for the rest of the session.",
                "Cancel non-essential pending orders.",
                "Write a loss review before considering the next session.",
                "Reduce the next session to demo or read-only observation.",
            ]
        )
        return GuardDecision(
            level="hard_stop",
            trade_allowed=False,
            reasons=reasons,
            required_actions=actions,
        )

    if caution:
        actions.extend(
            [
                "Wait through the cooldown before any new trade.",
                "Write entry, invalidation, size, and max loss before acting.",
                "Use smaller size or demo mode until execution quality normalizes.",
            ]
        )
        return GuardDecision(
            level="caution",
            trade_allowed=False,
            reasons=reasons,
            required_actions=actions,
        )

    return GuardDecision(
        level="clear",
        trade_allowed=True,
        reasons=["within configured behavioral risk limits"],
        required_actions=["Continue to use predefined size and invalidation rules."],
    )
