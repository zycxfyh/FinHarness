from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from finharness.data_entry import fetch_yfinance_history
from finharness.indicators.shared import latest_snapshot

ROOT = Path(__file__).resolve().parents[1]
FEATURE_DIR = ROOT / "data" / "features"


def run_indicator_cli(
    *,
    indicator: str,
    compute: Callable[[pd.DataFrame], pd.DataFrame],
    description: str,
) -> None:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-06-30")
    args = parser.parse_args()

    history = fetch_yfinance_history(args.symbol, args.start, args.end)
    features = compute(history)
    snapshot = latest_snapshot(
        args.symbol,
        history,
        features,
        indicator=indicator,
        source={
            "provider": "yfinance",
            "start": args.start,
            "end": args.end,
            "note": "Feature snapshot only; execution is not allowed from this layer.",
        },
    )
    write_snapshot(args.symbol, indicator, snapshot)


def write_snapshot(symbol: str, indicator: str, snapshot: dict[str, Any]) -> None:
    FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FEATURE_DIR / f"{symbol.lower()}_{indicator}_snapshot.json"
    output_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"symbol={snapshot['symbol']}")
    print(f"indicator={snapshot['indicator']}")
    print(f"rows={snapshot['rows']}")
    print(f"latest_date={snapshot['latest_date']}")
    print(f"output_path={output_path.relative_to(ROOT)}")
    print("execution_allowed=false")
