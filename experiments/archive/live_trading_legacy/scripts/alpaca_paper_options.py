"""Query Alpaca paper option contracts for an underlying symbol."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error

from finharness.alpaca_client import AlpacaPaperClient, query_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--underlying", default="SPY")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--type", choices=["call", "put"], default=None)
    parser.add_argument("--expiration-date-lte", default=None)
    parser.add_argument("--expiration-date-gte", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = AlpacaPaperClient()
    path = query_path(
        "/v2/options/contracts",
        {
            "underlying_symbols": args.underlying.upper(),
            "limit": args.limit,
            "type": args.type,
            "expiration_date_lte": args.expiration_date_lte,
            "expiration_date_gte": args.expiration_date_gte,
        },
    )

    try:
        response = client.get(path)
    except urllib.error.HTTPError as exc:
        print(f"alpaca_http_error={exc.code}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"alpaca_error={exc}", file=sys.stderr)
        return 1

    if not isinstance(response, dict):
        print("alpaca_error=unexpected response shape", file=sys.stderr)
        return 1

    contracts = response.get("option_contracts", [])
    if not isinstance(contracts, list):
        print("alpaca_error=unexpected option contract shape", file=sys.stderr)
        return 1

    rows = [
        {
            "symbol": contract.get("symbol"),
            "underlying_symbol": contract.get("underlying_symbol"),
            "type": contract.get("type"),
            "style": contract.get("style"),
            "strike_price": contract.get("strike_price"),
            "expiration_date": contract.get("expiration_date"),
            "tradable": contract.get("tradable"),
            "open_interest": contract.get("open_interest"),
            "close_price": contract.get("close_price"),
        }
        for contract in contracts
        if isinstance(contract, dict)
    ]
    print(
        json.dumps(
            {
                "environment": "paper",
                "underlying": args.underlying.upper(),
                "returned": len(rows),
                "next_page_token": response.get("next_page_token"),
                "contracts": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
