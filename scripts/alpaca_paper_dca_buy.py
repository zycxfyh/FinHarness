"""Place real paper DCA accumulation buys (one receipt per buy).

Unlike ``alpaca_paper_strategy_order.py`` (a deliberately non-fillable pipeline
validation order that is canceled immediately), this places marketable buys
meant to actually fill, to accumulate a long-term basic-investor position by a
fixed schedule. Each buy is one track-record event with its own receipt.

This is a thin adapter+guard+receipt workflow: order semantics belong to Alpaca,
behavioral bounds belong to the trading guard. It is paper-only and is not
investment advice.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
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
RECEIPTS = ROOT / "data" / "receipts" / "alpaca-paper-dca"
ALPACA_DCA_MARKET_ACCESS_LIMIT = MarketAccessLimit(
    max_window_notional=1000.0,
    max_window_order_count=20,
)

DEFAULT_THESIS = (
    "Basic-investor dollar-cost-averaging into broad-market ETFs on a fixed "
    "schedule. No market timing; hold long term; short-term indicators are "
    "treated as noise."
)
DEFAULT_INVALIDATION = (
    "Re-evaluate only if the long-term plan itself changes (income, goal, time "
    "horizon) — not on price moves or short-term signals."
)


@dataclass(frozen=True)
class DcaBuyPlan:
    schedule_id: str
    symbol: str
    side: str
    qty: str | None
    notional: str | None
    order_type: str
    latest_price: str | None
    thesis: str
    invalidation: str
    method: str  # fixed_share vs fixed_dollar, recorded honestly
    not_investment_advice: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", default="SPY,QQQ")
    parser.add_argument("--qty", default="1")
    parser.add_argument(
        "--notional",
        type=float,
        default=None,
        help=(
            "Dollar amount per symbol for fixed-dollar (true DCA) via fractional "
            "orders. When set, overrides --qty."
        ),
    )
    parser.add_argument("--thesis", default=DEFAULT_THESIS)
    parser.add_argument("--invalidation", default=DEFAULT_INVALIDATION)
    parser.add_argument("--drawdown-pct", type=float, default=0.0)
    parser.add_argument("--consecutive-losses", type=int, default=0)
    parser.add_argument("--cooldown-minutes", type=int, default=999)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Place the buys. Without this flag, only write dry-run receipts.",
    )
    parser.add_argument(
        "--operator",
        default="",
        help="Named operator required when --execute consumes market-access budget.",
    )
    return parser.parse_args()


def latest_price(client: AlpacaPaperClient, symbol: str) -> Decimal | None:
    """Best-effort latest trade price for receipt context. Never fatal."""
    try:
        trade = client.get(f"/v2/stocks/{symbol}/trades/latest", data_api=True)
    except Exception:
        return None
    if not isinstance(trade, dict):
        return None
    price = trade.get("trade", {}).get("p")
    return Decimal(str(price)) if price is not None else None


def place_market_buy(
    client: AlpacaPaperClient,
    symbol: str,
    *,
    qty: str | None = None,
    notional: float | None = None,
) -> dict:
    client_order_id = f"finharness-dca-{int(time.time())}-{uuid4().hex[:8]}"
    body = {
        "symbol": symbol,
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
        "client_order_id": client_order_id,
    }
    if notional is not None:
        body["notional"] = str(notional)  # fixed-dollar / fractional
    else:
        body["qty"] = str(qty)
    order = client.post("/v2/orders", body)
    if not isinstance(order, dict) or not order.get("id"):
        raise RuntimeError(f"Unexpected order response: {order}")
    return order


def write_receipt(receipt: dict) -> Path:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RECEIPTS / f"{stamp}-dca-{receipt['plan']['symbol']}.json"
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


def bounded_plan_notional(plan: DcaBuyPlan) -> float | None:
    if plan.notional is not None:
        return float(plan.notional)
    if plan.qty is None or plan.latest_price is None:
        return None
    return float(Decimal(plan.qty) * Decimal(plan.latest_price))


def main() -> int:
    args = parse_args()
    client = AlpacaPaperClient()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("dca_error=no symbols", file=sys.stderr)
        return 1

    try:
        account = client.get("/v2/account")
        clock = client.get("/v2/clock")
    except urllib.error.HTTPError as exc:
        print(f"alpaca_http_error={exc.code}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"alpaca_error={exc}", file=sys.stderr)
        return 1
    if not isinstance(account, dict):
        print("alpaca_error=unexpected account response", file=sys.stderr)
        return 1

    market_open = bool(clock.get("is_open")) if isinstance(clock, dict) else None
    account_ok = account.get("status") == "ACTIVE" and not account.get("trading_blocked")

    # Behavioral guard is account-level; evaluate once per run.
    guard = evaluate_trading_state(
        TradingState(
            drawdown_pct=args.drawdown_pct,
            consecutive_losses=args.consecutive_losses,
            minutes_since_last_trade=args.cooldown_minutes,
            planned_trade_has_written_thesis=True,
        )
    )

    may_execute = bool(args.execute and guard.trade_allowed and account_ok)
    use_dollar = args.notional is not None
    method = "fixed_dollar" if use_dollar else "fixed_share"
    results = []
    for symbol in symbols:
        price = latest_price(client, symbol)
        plan = DcaBuyPlan(
            schedule_id="basic_investor_dca_v1",
            symbol=symbol,
            side="buy",
            qty=None if use_dollar else args.qty,
            notional=str(args.notional) if use_dollar else None,
            order_type="market",
            latest_price=str(price) if price is not None else None,
            thesis=args.thesis,
            invalidation=args.invalidation,
            method=method,
            not_investment_advice=True,
        )
        order = None
        error = None
        market_access = {
            "evaluated": False,
            "allowed_within_limit": False,
            "blocking_reasons": [],
            "entry_id": None,
            "execution_allowed": False,
        }
        if may_execute:
            try:
                if not args.operator.strip():
                    raise MarketAccessLedgerError(
                        "named operator is required before paper execution"
                    )
                key = market_access_key(
                    account=account,
                    operator=args.operator,
                    symbol=symbol,
                )
                decision = evaluate_market_access(
                    key=key,
                    notional=bounded_plan_notional(plan),
                    limit=ALPACA_DCA_MARKET_ACCESS_LIMIT,
                    ledger=load_market_access_ledger(),
                )
                market_access = decision.model_dump(mode="json") | {
                    "evaluated": True,
                    "entry_id": None,
                }
                if decision.allowed_within_limit:
                    entry = record_consumption(
                        key=key,
                        notional=bounded_plan_notional(plan),
                        limit=ALPACA_DCA_MARKET_ACCESS_LIMIT,
                        source_ref=f"alpaca_dca_pre_submit:{symbol}",
                    )
                    market_access["entry_id"] = entry.entry_id
                    order = place_market_buy(
                        client,
                        symbol,
                        qty=None if use_dollar else args.qty,
                        notional=args.notional if use_dollar else None,
                    )
            except urllib.error.HTTPError as exc:
                error = exc.read().decode("utf-8", errors="replace")
            except MarketAccessLedgerError as exc:
                error = str(exc)
                market_access["blocking_reasons"] = [str(exc)]
            except Exception as exc:  # noqa: BLE001 - record, do not crash the batch
                error = str(exc)

        receipt = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "dry_run": not args.execute,
            "broker": "alpaca",
            "environment": "paper",
            "market_open": market_open,
            "plan": asdict(plan),
            "pre_trade": {
                "account_status": account.get("status"),
                "trading_blocked": account.get("trading_blocked"),
                "buying_power": account.get("buying_power"),
            },
            "risk_gate": asdict(guard),
            "market_access": market_access,
            "execution": {
                "attempted": bool(
                    may_execute and market_access.get("allowed_within_limit")
                ),
                "order": order,
                "error": error,
            },
        }
        path = write_receipt(receipt)
        results.append(
            {
                "symbol": symbol,
                "receipt_path": str(path),
                "latest_price": plan.latest_price,
                "order_id": order.get("id") if isinstance(order, dict) else None,
                "order_status": order.get("status") if isinstance(order, dict) else None,
                "error": error,
                "market_access": market_access,
            }
        )

    print(
        json.dumps(
            {
                "schedule_id": "basic_investor_dca_v1",
                "market_open": market_open,
                "method": method,
                "risk_gate": asdict(guard),
                "executed": any(item["order_id"] for item in results),
                "buys": results,
                "not_investment_advice": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    # Non-zero only if we tried to execute but something blocked every buy.
    if args.execute and not may_execute:
        return 1
    if args.execute and all(r["error"] for r in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
