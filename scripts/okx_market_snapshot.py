"""Fetch read-only OKX market snapshots through the official CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.okx_cli import okx_ticker

ROOT = Path(__file__).resolve().parents[1]
WATCHLIST = ROOT / "data" / "watchlists" / "okx-app-self-selected.yaml"


def read_watchlist_symbols(path: Path = WATCHLIST) -> list[str]:
    symbols: list[str] = []
    in_symbols = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line == "symbols:":
            in_symbols = True
            continue
        if in_symbols and line.startswith("- "):
            symbols.append(line[2:].strip())
        elif in_symbols and line and not line.startswith("#"):
            break
    return symbols


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("symbols", nargs="*", help="OKX symbols, e.g. BTC-USDT or BTCUSDT")
    parser.add_argument("--watchlist", action="store_true", help="Use local OKX app watchlist")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()

    symbols = args.symbols
    if args.watchlist:
        symbols = read_watchlist_symbols()[: args.limit]
    if not symbols:
        symbols = ["BTC-USDT"]

    snapshots = []
    for symbol in symbols[: args.limit]:
        try:
            snapshots.append({"symbol": symbol, "ok": True, "ticker": okx_ticker(symbol)})
        except Exception as exc:  # CLI failures should not hide other symbols.
            snapshots.append({"symbol": symbol, "ok": False, "error": str(exc)})

    print(json.dumps({"source": "okx_cli_public_market", "snapshots": snapshots}, indent=2))


if __name__ == "__main__":
    main()
