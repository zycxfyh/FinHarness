from __future__ import annotations

from _indicator_cli import run_indicator_cli
from finharness.indicators.squeeze import compute_squeeze_momentum

if __name__ == "__main__":
    run_indicator_cli(
        indicator="squeeze",
        compute=compute_squeeze_momentum,
        description="Run Squeeze Momentum feature snapshot.",
    )
