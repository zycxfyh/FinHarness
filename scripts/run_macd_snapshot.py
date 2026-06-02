from __future__ import annotations

from _indicator_cli import run_indicator_cli
from finharness.indicators.macd import compute_macd

if __name__ == "__main__":
    run_indicator_cli(
        indicator="macd",
        compute=compute_macd,
        description="Run MACD feature snapshot.",
    )
