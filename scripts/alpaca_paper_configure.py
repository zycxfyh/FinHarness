"""Configure the Alpaca paper account for broad experimentation."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error

from finharness.alpaca_client import AlpacaPaperClient, paper_experiment_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Patch the paper account. Without this flag the script only prints the payload.",
    )
    parser.add_argument(
        "--max-options-level",
        choices=["0", "1", "2", "3"],
        default="3",
        help="Desired max paper options level.",
    )
    parser.add_argument(
        "--max-margin-multiplier",
        choices=["1", "2", "4"],
        default="4",
        help="Desired paper margin multiplier.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = paper_experiment_config() | {
        "max_options_trading_level": int(args.max_options_level),
        "max_margin_multiplier": args.max_margin_multiplier,
    }

    if not args.apply:
        print(json.dumps({"dry_run": True, "environment": "paper", "payload": payload}, indent=2))
        return 0

    client = AlpacaPaperClient()
    try:
        before = client.get("/v2/account/configurations")
        updated = client.patch("/v2/account/configurations", payload)
    except urllib.error.HTTPError as exc:
        print(f"alpaca_http_error={exc.code}", file=sys.stderr)
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"alpaca_error={exc}", file=sys.stderr)
        return 1

    if not isinstance(before, dict) or not isinstance(updated, dict):
        print("alpaca_error=unexpected response shape", file=sys.stderr)
        return 1

    changed = {
        key: {"before": before.get(key), "after": updated.get(key)}
        for key in payload
        if before.get(key) != updated.get(key)
    }
    print(
        json.dumps(
            {
                "dry_run": False,
                "environment": "paper",
                "requested": payload,
                "changed": changed,
                "configuration": updated,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
