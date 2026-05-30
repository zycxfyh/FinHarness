"""Inspect Alpaca paper account capabilities and configuration."""

from __future__ import annotations

import json
import sys
import urllib.error

from finharness.alpaca_client import AlpacaPaperClient, summarize_account


def main() -> int:
    client = AlpacaPaperClient()
    try:
        account = client.get("/v2/account")
        config = client.get("/v2/account/configurations")
        positions = client.get("/v2/positions")
        orders = client.get("/v2/orders?status=all&limit=20&direction=desc")
        activities = client.get("/v2/account/activities?direction=desc&page_size=20")
    except urllib.error.HTTPError as exc:
        print(f"alpaca_http_error={exc.code}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"alpaca_error={exc}", file=sys.stderr)
        return 1

    if (
        not isinstance(account, dict)
        or not isinstance(config, dict)
        or not isinstance(positions, list)
        or not isinstance(orders, list)
        or not isinstance(activities, list)
    ):
        print("alpaca_error=unexpected response shape", file=sys.stderr)
        return 1

    summary = {
        "environment": "paper",
        "account": summarize_account(account),
        "configuration": {
            "suspend_trade": config.get("suspend_trade"),
            "no_shorting": config.get("no_shorting"),
            "fractional_trading": config.get("fractional_trading"),
            "max_margin_multiplier": config.get("max_margin_multiplier"),
            "max_options_trading_level": config.get("max_options_trading_level"),
            "disable_overnight_trading": config.get("disable_overnight_trading"),
            "trade_confirm_email": config.get("trade_confirm_email"),
            "dtbp_check": config.get("dtbp_check"),
            "pdt_check": config.get("pdt_check"),
        },
        "positions_count": len(positions),
        "recent_orders_count": len(orders),
        "recent_activities_count": len(activities),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
