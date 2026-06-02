from __future__ import annotations

import argparse
import json
from pathlib import Path

from finharness.data_entry import fetch_yfinance_history
from finharness.indicators.macd import compute_macd
from finharness.indicators.shared import clean_values
from finharness.indicators.smc import compute_smc
from finharness.indicators.squeeze import compute_squeeze_momentum

ROOT = Path(__file__).resolve().parents[1]
FEATURE_DIR = ROOT / "data" / "features"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MACD, Squeeze, and SMC-lite features.")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-06-30")
    args = parser.parse_args()

    history = fetch_yfinance_history(args.symbol, args.start, args.end)
    latest = history.index[-1]
    snapshot = {
        "symbol": args.symbol.upper(),
        "indicator": "combined",
        "rows": len(history),
        "latest_date": str(history.loc[latest, "date"]),
        "features": {
            "macd": clean_values(compute_macd(history).loc[latest].to_dict()),
            "squeeze": clean_values(compute_squeeze_momentum(history).loc[latest].to_dict()),
            "smc": clean_values(compute_smc(history).loc[latest].to_dict()),
        },
        "execution_allowed": False,
    }
    snapshot["source"] = {
        "provider": "yfinance",
        "start": args.start,
        "end": args.end,
        "note": "Feature snapshot only; execution is not allowed from this layer.",
    }

    FEATURE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = FEATURE_DIR / f"{args.symbol.lower()}_combined_indicator_snapshot.json"
    output_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"symbol={snapshot['symbol']}")
    print("indicator=combined")
    print(f"rows={snapshot['rows']}")
    print(f"latest_date={snapshot['latest_date']}")
    print(f"output_path={output_path.relative_to(ROOT)}")
    print("execution_allowed=false")


if __name__ == "__main__":
    main()
