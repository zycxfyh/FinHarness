from __future__ import annotations

import argparse
import importlib.util

import backtrader as bt
import pandas as pd
import yfinance as yf
from agents import Agent, Runner, function_tool
from deepeval.test_case import LLMTestCase
from openbb import obb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--network", action="store_true", help="Run provider-backed network checks")
    args = parser.parse_args()

    print("installed_core_wheels")
    print(f"backtrader={bt.__version__}")
    print(f"pandas={pd.__version__}")
    print(f"yfinance={yf.__version__}")
    print(f"agents={Agent.__name__}/{Runner.__name__}/{function_tool.__name__}")
    print(f"deepeval={LLMTestCase.__name__}")
    print(f"openbb={type(obb).__name__}")
    print()
    print("target_top_wheels")
    for module in ["vectorbt", "nautilus_trader", "riskfolio", "quantstats"]:
        status = "installed" if importlib.util.find_spec(module) else "missing"
        print(f"{module}={status}")

    if args.network:
        print()
        print("provider_network_checks")
        quote = obb.equity.price.quote("SPY", provider="yfinance").to_df()
        print(f"openbb_quote_rows={len(quote)}")


if __name__ == "__main__":
    main()
