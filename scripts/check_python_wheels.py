from __future__ import annotations

import argparse
import importlib.util

import backtrader as bt
import pandas as pd
import yfinance as yf
from agents import Agent, Runner, function_tool
from deepeval.test_case import LLMTestCase


def load_openbb_app():
    if not importlib.util.find_spec("openbb"):
        return None
    try:
        from openbb import obb
    except ImportError:
        return None

    return obb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", action="store_true", help="Run provider-backed network checks")
    args = parser.parse_args()
    openbb_app = load_openbb_app()

    print("installed_core_wheels")
    print(f"backtrader={bt.__version__}")
    print(f"pandas={pd.__version__}")
    print(f"yfinance={yf.__version__}")
    print(f"agents={Agent.__name__}/{Runner.__name__}/{function_tool.__name__}")
    print(f"deepeval={LLMTestCase.__name__}")
    if openbb_app is None:
        print("openbb=optional-missing")
    else:
        print(f"openbb=optional-installed:{type(openbb_app).__name__}")
    print()
    print("target_top_wheels")
    for module in ["vectorbt", "nautilus_trader", "riskfolio", "quantstats"]:
        status = "installed" if importlib.util.find_spec(module) else "missing"
        print(f"{module}={status}")

    if args.network:
        print()
        print("provider_network_checks")
        history = yf.download(
            "SPY",
            period="5d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
        print(f"yfinance_history_rows={len(history)}")
        if openbb_app is None:
            print("openbb_quote_rows=skipped_optional_missing")
        else:
            quote = openbb_app.equity.price.quote("SPY", provider="yfinance").to_df()
            print(f"openbb_quote_rows={len(quote)}")


if __name__ == "__main__":
    main()
