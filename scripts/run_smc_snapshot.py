from __future__ import annotations

from _indicator_cli import run_indicator_cli
from finharness.indicators.smc import compute_smc

if __name__ == "__main__":
    run_indicator_cli(
        indicator="smc",
        compute=compute_smc,
        description="Run SMC/MSB-OB feature snapshot.",
    )
