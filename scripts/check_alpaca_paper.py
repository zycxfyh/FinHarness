"""Check Alpaca paper trading account access without printing credentials."""

from __future__ import annotations

import json
import sys
import urllib.error

from finharness.alpaca_client import PAPER_BASE_URL, AlpacaPaperClient, summarize_account


def main() -> int:
    client = AlpacaPaperClient()
    try:
        account = client.get("/v2/account")
        positions = client.get("/v2/positions")
        orders = client.get("/v2/orders?status=open&limit=50")
    except urllib.error.HTTPError as exc:
        print(f"alpaca_http_error={exc.code}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"alpaca_error={exc}", file=sys.stderr)
        return 1

    if (
        not isinstance(account, dict)
        or not isinstance(positions, list)
        or not isinstance(orders, list)
    ):
        print("alpaca_error=unexpected response shape", file=sys.stderr)
        return 1

    summary = {
        "paper_base_url": PAPER_BASE_URL,
        **summarize_account(account),
        "positions_count": len(positions),
        "open_orders_count": len(orders),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
