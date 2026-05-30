"""List Alpaca paper tradable assets by class."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error

from finharness.alpaca_client import AlpacaPaperClient, query_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--asset-class",
        choices=["us_equity", "crypto", "us_option"],
        default="us_equity",
    )
    parser.add_argument("--status", default="active")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--attributes", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = AlpacaPaperClient()
    path = query_path(
        "/v2/assets",
        {
            "status": args.status,
            "asset_class": args.asset_class,
            "attributes": args.attributes,
        },
    )

    try:
        assets = client.get(path)
    except urllib.error.HTTPError as exc:
        print(f"alpaca_http_error={exc.code}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"alpaca_error={exc}", file=sys.stderr)
        return 1

    if not isinstance(assets, list):
        print("alpaca_error=unexpected response shape", file=sys.stderr)
        return 1

    rows = [
        {
            "symbol": asset.get("symbol"),
            "name": asset.get("name"),
            "class": asset.get("class"),
            "exchange": asset.get("exchange"),
            "status": asset.get("status"),
            "tradable": asset.get("tradable"),
            "marginable": asset.get("marginable"),
            "shortable": asset.get("shortable"),
            "fractionable": asset.get("fractionable"),
            "attributes": asset.get("attributes"),
        }
        for asset in assets[: args.limit]
        if isinstance(asset, dict)
    ]
    print(
        json.dumps(
            {
                "environment": "paper",
                "asset_class": args.asset_class,
                "returned": len(assets),
                "shown": len(rows),
                "assets": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
