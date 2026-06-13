"""Persistent behavioral trading state shared across risk-gate runs.

This closes the Loop 3 feedback edge: post-trade outcomes update one durable
TradingStateRecord, and the next risk-gate run reads it instead of trusting a
hand-fed risk_context. The store is state, not evidence; receipts remain the
evidence layer and the record always points back at its source receipts.

Honesty rule: fake paper fills carry no P&L, so this store never invents
win/loss outcomes. Trade occurrence and process failures update automatically;
win/loss/drawdown updates require an explicit operator report.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.market_data import ROOT

TRADING_STATE_ENV_VAR = "FINHARNESS_TRADING_STATE_PATH"
DEFAULT_TRADING_STATE_PATH = ROOT / "data" / "state" / "trading-state.json"

TradeOutcome = Literal["win", "loss", "flat"]

# Post-trade statuses that prove a trade lifecycle actually completed.
TRADE_OCCURRED_STATUSES = frozenset(
    {"reconciled_filled", "reconciled_canceled", "partial_fill_exception"}
)
# Post-trade statuses that signal a process-integrity failure. These trip the
# behavior reset flag so the next risk-gate run fails closed until a human
# clears it.
PROCESS_FAILURE_STATUSES = frozenset({"lineage_failed", "needs_human_review"})


class TradingStateRecord(BaseModel):
    """Durable behavioral state consumed by the risk gate."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "finharness.trading_state.v1"
    drawdown_pct: float = 0.0
    consecutive_losses: int = 0
    trades_recorded: int = 0
    last_trade_at_utc: str | None = None
    behavior_reset_required: bool = False
    behavior_reset_reason: str | None = None
    last_outcome: TradeOutcome | None = None
    source_refs: list[str] = Field(default_factory=list)
    updated_at_utc: str | None = None
    notes: list[str] = Field(default_factory=list)


def trading_state_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    env_path = os.environ.get(TRADING_STATE_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_TRADING_STATE_PATH


def load_trading_state(path: str | Path | None = None) -> TradingStateRecord:
    """Load persisted state; a missing or unreadable file yields safe defaults."""
    target = trading_state_path(path)
    if not target.exists():
        return TradingStateRecord()
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        return TradingStateRecord.model_validate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        # A corrupt state file must not silently grant a clean slate for
        # drawdown/losses; fail closed by requiring a human reset.
        return TradingStateRecord(
            behavior_reset_required=True,
            behavior_reset_reason=f"trading state file unreadable: {exc}",
            notes=[f"unreadable state file at {target}"],
        )


def save_trading_state(
    record: TradingStateRecord, path: str | Path | None = None
) -> Path:
    target = trading_state_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(target)
    return target


def _now_utc() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _appended_refs(record: TradingStateRecord, ref: str | None, *, cap: int = 50) -> list[str]:
    refs = list(record.source_refs)
    if ref:
        refs.append(ref)
    return refs[-cap:]


def record_operator_outcome(
    *,
    outcome: TradeOutcome,
    drawdown_pct: float,
    receipt_ref: str | None = None,
    path: str | Path | None = None,
) -> TradingStateRecord:
    """Apply an operator-reported trade outcome (the only source of win/loss)."""
    record = load_trading_state(path)
    consecutive = record.consecutive_losses + 1 if outcome == "loss" else 0
    updated = record.model_copy(
        update={
            "drawdown_pct": drawdown_pct,
            "consecutive_losses": consecutive,
            "trades_recorded": record.trades_recorded + 1,
            "last_trade_at_utc": _now_utc(),
            "last_outcome": outcome,
            "source_refs": _appended_refs(record, receipt_ref),
            "updated_at_utc": _now_utc(),
        }
    )
    save_trading_state(updated, path)
    return updated


def update_from_post_trade_snapshot(
    snapshot: dict[str, Any],
    *,
    path: str | Path | None = None,
) -> TradingStateRecord:
    """Fold a post-trade snapshot into persisted state.

    Only facts the snapshot can prove are recorded: that a trade lifecycle
    completed, and that a process failure occurred. Win/loss is never inferred
    from fake-adapter fills.
    """
    record = load_trading_state(path)
    status = str(snapshot.get("final_status") or snapshot.get("post_trade_status") or "")
    receipt_ref = snapshot.get("receipt_ref")
    updates: dict[str, Any] = {
        "source_refs": _appended_refs(record, receipt_ref),
        "updated_at_utc": _now_utc(),
    }
    if status in TRADE_OCCURRED_STATUSES:
        updates["trades_recorded"] = record.trades_recorded + 1
        updates["last_trade_at_utc"] = _now_utc()
    if status in PROCESS_FAILURE_STATUSES:
        updates["behavior_reset_required"] = True
        updates["behavior_reset_reason"] = f"post-trade status {status}"
    updated = record.model_copy(update=updates)
    save_trading_state(updated, path)
    return updated


def record_live_order_placed(
    *,
    receipt_ref: str | None = None,
    path: str | Path | None = None,
) -> TradingStateRecord:
    """Fold a placed live order into persisted state (closes Loop 3 for the
    live path, red-team F5).

    Records only the honest fact that a live order was placed: trade occurrence
    and its source receipt. Win/loss/drawdown stay operator-reported via
    record_operator_outcome — a placed order is not a known outcome.
    """
    record = load_trading_state(path)
    updated = record.model_copy(
        update={
            "trades_recorded": record.trades_recorded + 1,
            "last_trade_at_utc": _now_utc(),
            "source_refs": _appended_refs(record, receipt_ref),
            "updated_at_utc": _now_utc(),
        }
    )
    save_trading_state(updated, path)
    return updated


def reset_behavior_flag(
    *,
    reason: str,
    path: str | Path | None = None,
) -> TradingStateRecord:
    """Human-only action: clear the behavior reset flag with a written reason."""
    record = load_trading_state(path)
    updated = record.model_copy(
        update={
            "behavior_reset_required": False,
            "behavior_reset_reason": None,
            "notes": [*record.notes, f"behavior flag cleared: {reason}"][-20:],
            "updated_at_utc": _now_utc(),
        }
    )
    save_trading_state(updated, path)
    return updated


def merge_into_risk_context(
    risk_context: dict[str, Any] | None,
    *,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Merge persisted behavioral state into a risk context conservatively.

    Persisted protective state is a floor, not a default. An explicitly supplied
    value may only make the gate *stricter*, never weaker: a hand-fed clean
    context can no longer erase a persisted drawdown, loss streak, or reset
    flag. This is the fail-closed behavior the Loop 3 feedback edge requires —
    the previous setdefault let a clean hand-fed context override a tripped hard
    stop (red-team finding F6, 2026-06-13).
    """
    context = dict(risk_context or {})
    record = load_trading_state(path)

    # Drawdown is negative when down; the more negative (worse) value wins.
    if "drawdown_pct" in context:
        try:
            context["drawdown_pct"] = min(
                float(context["drawdown_pct"]), record.drawdown_pct
            )
        except (TypeError, ValueError):
            context["drawdown_pct"] = record.drawdown_pct
    else:
        context["drawdown_pct"] = record.drawdown_pct

    # A longer loss streak is stricter; the larger value wins.
    if "consecutive_losses" in context:
        try:
            context["consecutive_losses"] = max(
                int(context["consecutive_losses"]), record.consecutive_losses
            )
        except (TypeError, ValueError):
            context["consecutive_losses"] = record.consecutive_losses
    else:
        context["consecutive_losses"] = record.consecutive_losses

    # A reset requirement from either source must stand.
    context["behavior_reset_required"] = (
        bool(context.get("behavior_reset_required", False))
        or record.behavior_reset_required
    )

    return context
