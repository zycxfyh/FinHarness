"""Place and cancel a tiny Alpaca paper limit order."""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
from decimal import ROUND_DOWN, Decimal
from uuid import uuid4

from finharness.alpaca_client import PAPER_BASE_URL, AlpacaPaperClient


def latest_price(client: AlpacaPaperClient, symbol: str) -> Decimal:
    trade = client.get(f"/v2/stocks/{symbol}/trades/latest", data_api=True)
    if not isinstance(trade, dict):
        raise RuntimeError(f"Unexpected latest trade response for {symbol}: {trade}")
    price = trade.get("trade", {}).get("p")
    if price is None:
        raise RuntimeError(f"No latest trade price returned for {symbol}: {trade}")
    return Decimal(str(price))


def far_below_market(price: Decimal) -> str:
    # Low enough to avoid accidental fill while still a valid positive price.
    target = (price * Decimal("0.50")).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return str(max(target, Decimal("1.00")))


def main() -> int:
    client = AlpacaPaperClient()
    symbol = os.environ.get("ALPACA_TEST_SYMBOL", "AAPL").upper()
    qty = os.environ.get("ALPACA_TEST_QTY", "1")

    try:
        price = latest_price(client, symbol)
        limit_price = far_below_market(price)
        client_order_id = f"finharness-{int(time.time())}-{uuid4().hex[:8]}"
        order = client.post(
            "/v2/orders",
            {
                "symbol": symbol,
                "qty": qty,
                "side": "buy",
                "type": "limit",
                "time_in_force": "day",
                "limit_price": limit_price,
                "client_order_id": client_order_id,
            },
        )
        if not isinstance(order, dict):
            raise RuntimeError(f"Unexpected order response: {order}")
        order_id = order.get("id")
        if not order_id:
            raise RuntimeError(f"Order response missing id: {order}")

        fetched = client.get(f"/v2/orders/{order_id}")
        canceled = client.delete(f"/v2/orders/{order_id}")
        open_orders = client.get("/v2/orders?status=open&limit=50")
    except urllib.error.HTTPError as exc:
        print(f"alpaca_http_error={exc.code}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"alpaca_error={exc}", file=sys.stderr)
        return 1

    if (
        not isinstance(fetched, dict)
        or not isinstance(canceled, dict)
        or not isinstance(open_orders, list)
    ):
        print("alpaca_error=unexpected response shape", file=sys.stderr)
        return 1

    summary = {
        "paper_base_url": PAPER_BASE_URL,
        "symbol": symbol,
        "latest_price": str(price),
        "limit_price": limit_price,
        "qty": qty,
        "client_order_id": client_order_id,
        "order_id": order_id,
        "place_status": order.get("status"),
        "fetched_status": fetched.get("status"),
        "cancel_status": canceled.get("status"),
        "open_orders_count_after_cancel": len(open_orders),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
