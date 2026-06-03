"""Archived LangGraph trade workflow using paper execution adapters.

Archived on 2026-06-03 after Layers 7-10 split proposal, risk, execution, and
post-trade responsibilities into the authoritative ten-layer chain. Kept as
historical reference only; do not import from active source paths.
"""

from __future__ import annotations

import json
import time
import urllib.error
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from io import StringIO
from pathlib import Path
from typing import Any, TypedDict
from uuid import uuid4

import pandas as pd
import vectorbt as vbt
from langgraph.graph import END, START, StateGraph

from finharness.alpaca_client import AlpacaPaperClient
from finharness.market_data import fetch_yfinance_close_snapshot
from finharness.trading_guard import TradingState, evaluate_trading_state

ROOT = Path(__file__).resolve().parents[2]
RECEIPTS = ROOT / "data" / "receipts" / "alpaca-paper-langgraph"


class TradeGraphState(TypedDict, total=False):
    universe: list[str]
    fast_window: int
    slow_window: int
    order_qty: str
    execute: bool
    drawdown_pct: float
    consecutive_losses: int
    cooldown_minutes: int
    market_data: dict[str, Any]
    research: dict[str, Any]
    account: dict[str, Any]
    risk_gate: dict[str, Any]
    order_plan: dict[str, Any]
    execution: dict[str, Any]
    receipt_path: str
    final: dict[str, Any]


def market_data_node(state: TradeGraphState) -> TradeGraphState:
    universe = state.get("universe", ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"])
    bundle = fetch_yfinance_close_snapshot(universe)
    close = bundle.close
    return {
        "market_data": {
            "provider": "yfinance",
            "snapshot": bundle.snapshot.model_dump(mode="json"),
            "receipt_path": bundle.snapshot.receipt_ref,
            "rows": len(close),
            "symbols": list(close.columns),
            "last_close": {symbol: float(close[symbol].iloc[-1]) for symbol in close.columns},
            "_close_json": close.to_json(date_format="iso"),
        }
    }


def research_node(state: TradeGraphState) -> TradeGraphState:
    market_data = state["market_data"]
    close = pd.read_json(StringIO(market_data["_close_json"]))
    fast_window = state.get("fast_window", 20)
    slow_window = state.get("slow_window", 50)

    candidates: list[dict[str, Any]] = []
    for symbol in close.columns:
        series = close[symbol].dropna()
        fast_ma = vbt.MA.run(series, window=fast_window).ma
        slow_ma = vbt.MA.run(series, window=slow_window).ma
        entries = fast_ma > slow_ma
        exits = fast_ma < slow_ma
        portfolio = vbt.Portfolio.from_signals(series, entries, exits, init_cash=10_000.0)
        latest_signal = bool(entries.iloc[-1])
        candidates.append(
            {
                "symbol": symbol,
                "latest_close": float(series.iloc[-1]),
                "fast_ma": float(fast_ma.iloc[-1]),
                "slow_ma": float(slow_ma.iloc[-1]),
                "latest_signal": latest_signal,
                "vectorbt_total_return": float(portfolio.total_return()),
                "vectorbt_max_drawdown": float(portfolio.max_drawdown()),
            }
        )

    eligible = [
        candidate
        for candidate in candidates
        if candidate["latest_signal"] and candidate["vectorbt_total_return"] > 0
    ]
    selected = max(eligible, key=lambda item: item["vectorbt_total_return"]) if eligible else None
    return {
        "research": {
            "engine": "vectorbt",
            "hypothesis": f"{fast_window}/{slow_window} trend-following screen",
            "selection_rule": "latest fast MA > slow MA and positive vectorbt total return",
            "candidates": candidates,
            "selected": selected,
            "trade_intent": "paper_long_test" if selected else "no_trade",
        }
    }


def account_node(state: TradeGraphState) -> TradeGraphState:
    client = AlpacaPaperClient()
    account = client.get("/v2/account")
    positions = client.get("/v2/positions")
    open_orders = client.get("/v2/orders?status=open&limit=50")
    if (
        not isinstance(account, dict)
        or not isinstance(positions, list)
        or not isinstance(open_orders, list)
    ):
        raise ValueError("unexpected Alpaca account response shape")
    return {
        "account": {
            "broker": "alpaca",
            "environment": "paper",
            "status": account.get("status"),
            "portfolio_value": account.get("portfolio_value"),
            "buying_power": account.get("buying_power"),
            "trading_blocked": account.get("trading_blocked"),
            "account_blocked": account.get("account_blocked"),
            "positions_count": len(positions),
            "open_orders_before": len(open_orders),
        }
    }


def risk_gate_node(state: TradeGraphState) -> TradeGraphState:
    research = state["research"]
    account = state["account"]
    selected = research.get("selected")
    behavioral = evaluate_trading_state(
        TradingState(
            drawdown_pct=state.get("drawdown_pct", 0.0),
            consecutive_losses=state.get("consecutive_losses", 0),
            minutes_since_last_trade=state.get("cooldown_minutes", 999),
            planned_trade_has_written_thesis=selected is not None,
        )
    )

    reasons = list(behavioral.reasons)
    allowed = behavioral.trade_allowed
    if selected is None:
        allowed = False
        reasons.append("no eligible vectorbt research candidate")
    if account.get("status") != "ACTIVE":
        allowed = False
        reasons.append(f"account status is {account.get('status')}")
    if account.get("trading_blocked") or account.get("account_blocked"):
        allowed = False
        reasons.append("Alpaca account is blocked")
    if account.get("open_orders_before", 0) != 0:
        allowed = False
        reasons.append("open orders existed before workflow")

    return {
        "risk_gate": {
            "level": "clear" if allowed else "blocked",
            "trade_allowed": allowed,
            "behavioral_guard": asdict(behavioral),
            "reasons": reasons,
        }
    }


def order_plan_node(state: TradeGraphState) -> TradeGraphState:
    selected = state["research"].get("selected")
    if selected is None:
        return {"order_plan": {"action": "no_trade", "reason": "no selected research candidate"}}

    latest = Decimal(str(selected["latest_close"]))
    limit_price = (latest * Decimal("0.995")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    qty = state.get("order_qty", "1")
    notional = (Decimal(qty) * limit_price).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    account_value = Decimal(str(state["account"].get("portfolio_value", "0")))
    max_notional = (account_value * Decimal("0.01")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)

    return {
        "order_plan": {
            "action": "paper_limit_buy_then_cancel",
            "strategy_id": "langgraph_vectorbt_trend_v1",
            "symbol": selected["symbol"],
            "side": "buy",
            "qty": qty,
            "latest_close": str(latest),
            "limit_price": str(limit_price),
            "estimated_notional": str(notional),
            "max_notional_budget": str(max_notional),
            "within_notional_budget": notional <= max_notional,
            "thesis": (
                "Use vectorbt to select a positive 20/50 trend-following candidate, then "
                "exercise broker paper execution with a small limit order and immediate "
                "post-acceptance cancel."
            ),
            "invalidation": (
                "Do not continue if the research candidate disappears, account has open "
                "orders, notional exceeds budget, order fills unexpectedly, or cancel "
                "leaves an open order."
            ),
            "execution_algo": "limit order near latest close, immediate cancel after accepted",
        }
    }


def execution_node(state: TradeGraphState) -> TradeGraphState:
    plan = state["order_plan"]
    risk_gate = state["risk_gate"]
    should_execute = bool(state.get("execute", False))
    if (
        not should_execute
        or not risk_gate.get("trade_allowed")
        or not plan.get("within_notional_budget")
    ):
        return {
            "execution": {
                "attempted": False,
                "reason": "execute false, risk gate blocked, or notional budget failed",
            }
        }

    client = AlpacaPaperClient()
    client_order_id = f"finharness-lg-{int(time.time())}-{uuid4().hex[:8]}"
    try:
        order = client.post(
            "/v2/orders",
            {
                "symbol": plan["symbol"],
                "qty": plan["qty"],
                "side": plan["side"],
                "type": "limit",
                "time_in_force": "day",
                "limit_price": plan["limit_price"],
                "client_order_id": client_order_id,
            },
        )
        if not isinstance(order, dict) or not order.get("id"):
            raise ValueError(f"unexpected Alpaca order response: {order}")
        fetched = client.get(f"/v2/orders/{order['id']}")
        canceled = client.delete(f"/v2/orders/{order['id']}")
        open_orders_after = client.get("/v2/orders?status=open&limit=50")
    except urllib.error.HTTPError as exc:
        return {
            "execution": {
                "attempted": True,
                "ok": False,
                "http_error": exc.code,
                "body": exc.read().decode("utf-8", errors="replace"),
            }
        }

    return {
        "execution": {
            "attempted": True,
            "ok": isinstance(open_orders_after, list) and len(open_orders_after) == 0,
            "order": order,
            "fetched": fetched,
            "canceled": canceled,
            "open_orders_after": len(open_orders_after)
            if isinstance(open_orders_after, list)
            else None,
        }
    }


def receipt_node(state: TradeGraphState) -> TradeGraphState:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    symbol = state.get("order_plan", {}).get("symbol", "NO_SYMBOL")
    path = RECEIPTS / f"{stamp}-institutional-paper-flow-{symbol}.json"
    receipt = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "workflow": "langgraph_institutional_paper_trade_v1",
        "state": {
            key: value
            for key, value in state.items()
            if key not in {"market_data"} or not isinstance(value, dict)
        },
        "market_data_summary": {
            key: value
            for key, value in state.get("market_data", {}).items()
            if not key.startswith("_")
        },
    }
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"receipt_path": str(path)}


def final_node(state: TradeGraphState) -> TradeGraphState:
    execution = state.get("execution", {})
    return {
        "final": {
            "workflow": "langgraph_institutional_paper_trade_v1",
            "selected": state.get("research", {}).get("selected"),
            "risk_gate": state.get("risk_gate"),
            "order_plan": state.get("order_plan"),
            "execution_attempted": execution.get("attempted", False),
            "execution_ok": execution.get("ok", False),
            "receipt_path": state.get("receipt_path"),
        }
    }


def build_trade_graph():
    graph = StateGraph(TradeGraphState)
    graph.add_node("market_data", market_data_node)
    graph.add_node("research", research_node)
    graph.add_node("account", account_node)
    graph.add_node("risk_gate", risk_gate_node)
    graph.add_node("order_plan", order_plan_node)
    graph.add_node("execution", execution_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "market_data")
    graph.add_edge("market_data", "research")
    graph.add_edge("research", "account")
    graph.add_edge("account", "risk_gate")
    graph.add_edge("risk_gate", "order_plan")
    graph.add_edge("order_plan", "execution")
    graph.add_edge("execution", "receipt")
    graph.add_edge("receipt", "final")
    graph.add_edge("final", END)
    return graph.compile()


trade_graph = build_trade_graph()


def run_institutional_paper_trade(
    *,
    universe: list[str] | None = None,
    execute: bool = False,
    order_qty: str = "1",
) -> dict[str, Any]:
    result = trade_graph.invoke(
        {
            "universe": universe or ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"],
            "execute": execute,
            "order_qty": order_qty,
        }
    )
    return dict(result)
