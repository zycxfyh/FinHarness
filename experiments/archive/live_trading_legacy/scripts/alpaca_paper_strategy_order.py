"""Run a paper order with an explicit thesis, risk gate, and receipt."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from uuid import uuid4

from finharness.alpaca_client import AlpacaPaperClient
from finharness.market_access_ledger import (
    MarketAccessKey,
    MarketAccessLedgerError,
    MarketAccessLimit,
    evaluate_market_access,
    load_market_access_ledger,
    record_consumption,
)
from finharness.trading_guard import TradingState, evaluate_trading_state

ROOT = Path(__file__).resolve().parents[1]
RECEIPTS = ROOT / "data" / "receipts" / "alpaca-paper"
ALPACA_PAPER_MARKET_ACCESS_LIMIT = MarketAccessLimit(
    max_window_notional=1000.0,
    max_window_order_count=20,
)


@dataclass(frozen=True)
class StrategyOrderPlan:
    strategy_id: str
    symbol: str
    side: str
    qty: str
    latest_price: str
    limit_price: str
    thesis: str
    signal_evidence: list[str]
    order_reason: str
    invalidation: str
    risk_budget: dict[str, str]
    execution_intent: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--qty", default="1")
    parser.add_argument("--drawdown-pct", type=float, default=0.0)
    parser.add_argument("--consecutive-losses", type=int, default=0)
    parser.add_argument("--cooldown-minutes", type=int, default=999)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Place and cancel the paper order. Without this flag, only write a dry-run receipt.",
    )
    parser.add_argument(
        "--operator",
        default="",
        help="Named operator required when --execute consumes market-access budget.",
    )
    return parser.parse_args()


def latest_price(client: AlpacaPaperClient, symbol: str) -> Decimal:
    trade = client.get(f"/v2/stocks/{symbol}/trades/latest", data_api=True)
    if not isinstance(trade, dict):
        raise RuntimeError(f"Unexpected latest trade response for {symbol}: {trade}")
    price = trade.get("trade", {}).get("p")
    if price is None:
        raise RuntimeError(f"No latest trade price returned for {symbol}: {trade}")
    return Decimal(str(price))


def conservative_test_limit(price: Decimal) -> Decimal:
    return max(
        (price * Decimal("0.50")).quantize(Decimal("0.01"), rounding=ROUND_DOWN),
        Decimal("1.00"),
    )


def build_plan(symbol: str, qty: str, latest: Decimal, limit_price: Decimal) -> StrategyOrderPlan:
    notional = (Decimal(qty) * limit_price).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return StrategyOrderPlan(
        strategy_id="broker_pipeline_validation_v1",
        symbol=symbol,
        side="buy",
        qty=qty,
        latest_price=str(latest),
        limit_price=str(limit_price),
        thesis=(
            "This is not a directional alpha trade. The objective is to validate the "
            "broker-style paper execution workflow with a deliberately non-marketable "
            "limit order."
        ),
        signal_evidence=[
            f"Latest {symbol} trade price is {latest}.",
            f"Limit price is set near 50% of latest price at {limit_price}.",
            "The price gap makes immediate fill unlikely under normal market conditions.",
            "The order is canceled immediately after broker acceptance is confirmed.",
        ],
        order_reason=(
            "Exercise the institutional workflow shape: pre-check, written thesis, "
            "risk gate, order placement, order query, cancel, and reconciliation."
        ),
        invalidation=(
            "If the order fills, if open orders remain after cancel, or if account "
            "state is blocked, the workflow fails and must be reviewed before reuse."
        ),
        risk_budget={
            "environment": "paper",
            "max_quantity": qty,
            "max_limit_notional": str(notional),
            "expected_fill": "no_fill_expected",
            "live_capital_at_risk": "0",
        },
        execution_intent="day limit buy, far below market, immediate cancel after acceptance",
    )


def write_receipt(receipt: dict) -> Path:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RECEIPTS / f"{stamp}-{receipt['plan']['strategy_id']}-{receipt['plan']['symbol']}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def market_access_key(*, account: dict, operator: str, symbol: str) -> MarketAccessKey:
    return MarketAccessKey(
        environment="paper",
        venue="alpaca",
        operator=operator.strip(),
        account=str(account.get("id") or "alpaca_paper_account"),
        symbol=symbol.upper(),
    )


def main() -> int:
    args = parse_args()
    client = AlpacaPaperClient()
    symbol = args.symbol.upper()

    try:
        account = client.get("/v2/account")
        open_orders_before = client.get("/v2/orders?status=open&limit=50")
        latest = latest_price(client, symbol)
    except urllib.error.HTTPError as exc:
        print(f"alpaca_http_error={exc.code}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"alpaca_error={exc}", file=sys.stderr)
        return 1

    if not isinstance(account, dict) or not isinstance(open_orders_before, list):
        print("alpaca_error=unexpected response shape", file=sys.stderr)
        return 1

    limit_price = conservative_test_limit(latest)
    plan = build_plan(symbol, args.qty, latest, limit_price)
    guard = evaluate_trading_state(
        TradingState(
            drawdown_pct=args.drawdown_pct,
            consecutive_losses=args.consecutive_losses,
            minutes_since_last_trade=args.cooldown_minutes,
            planned_trade_has_written_thesis=True,
        )
    )

    order = None
    fetched = None
    canceled = None
    open_orders_after = None
    market_access = {
        "evaluated": False,
        "allowed_within_limit": False,
        "blocking_reasons": [],
        "entry_id": None,
        "execution_allowed": False,
    }
    if args.execute and guard.trade_allowed:
        try:
            if not args.operator.strip():
                raise MarketAccessLedgerError(
                    "named operator is required before paper execution"
                )
            key = market_access_key(
                account=account,
                operator=args.operator,
                symbol=plan.symbol,
            )
            notional = float(plan.risk_budget["max_limit_notional"])
            decision = evaluate_market_access(
                key=key,
                notional=notional,
                limit=ALPACA_PAPER_MARKET_ACCESS_LIMIT,
                ledger=load_market_access_ledger(),
            )
            market_access = decision.model_dump(mode="json") | {
                "evaluated": True,
                "entry_id": None,
            }
            if decision.allowed_within_limit:
                client_order_id = f"finharness-{int(time.time())}-{uuid4().hex[:8]}"
                entry = record_consumption(
                    key=key,
                    notional=notional,
                    limit=ALPACA_PAPER_MARKET_ACCESS_LIMIT,
                    source_ref=client_order_id,
                )
                market_access["entry_id"] = entry.entry_id
                order = client.post(
                    "/v2/orders",
                    {
                        "symbol": plan.symbol,
                        "qty": plan.qty,
                        "side": plan.side,
                        "type": "limit",
                        "time_in_force": "day",
                        "limit_price": plan.limit_price,
                        "client_order_id": client_order_id,
                    },
                )
                if not isinstance(order, dict) or not order.get("id"):
                    raise RuntimeError(f"Unexpected order response: {order}")
                fetched = client.get(f"/v2/orders/{order['id']}")
                canceled = client.delete(f"/v2/orders/{order['id']}")
                open_orders_after = client.get("/v2/orders?status=open&limit=50")
        except urllib.error.HTTPError as exc:
            print(f"alpaca_http_error={exc.code}", file=sys.stderr)
            print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
            return 1
        except MarketAccessLedgerError as exc:
            market_access["blocking_reasons"] = [str(exc)]
        except Exception as exc:
            print(f"alpaca_error={exc}", file=sys.stderr)
            return 1

    receipt = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "dry_run": not args.execute,
        "broker": "alpaca",
        "environment": "paper",
        "plan": asdict(plan),
        "pre_trade": {
            "account_status": account.get("status"),
            "trading_blocked": account.get("trading_blocked"),
            "account_blocked": account.get("account_blocked"),
            "positions_count_unknown_in_this_receipt": True,
            "open_orders_before": len(open_orders_before),
        },
        "risk_gate": asdict(guard),
        "market_access": market_access,
        "execution": {
            "attempted": bool(
                args.execute
                and guard.trade_allowed
                and market_access.get("allowed_within_limit")
            ),
            "order": order,
            "fetched": fetched,
            "canceled": canceled,
            "open_orders_after": len(open_orders_after)
            if isinstance(open_orders_after, list)
            else None,
        },
        "post_trade_assessment": {
            "workflow_passed": bool(
                args.execute
                and guard.trade_allowed
                and market_access.get("allowed_within_limit")
                and isinstance(open_orders_after, list)
                and len(open_orders_after) == 0
            ),
            "not_investment_advice": True,
            "not_alpha_validation": True,
        },
    }
    receipt_path = write_receipt(receipt)
    print(
        json.dumps(
            {
                "receipt_path": str(receipt_path),
                "strategy_id": plan.strategy_id,
                "symbol": plan.symbol,
                "thesis": plan.thesis,
                "order_reason": plan.order_reason,
                "risk_gate": asdict(guard),
                "execution": receipt["execution"],
                "post_trade_assessment": receipt["post_trade_assessment"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if receipt["post_trade_assessment"]["workflow_passed"] or not args.execute else 1


if __name__ == "__main__":
    raise SystemExit(main())
