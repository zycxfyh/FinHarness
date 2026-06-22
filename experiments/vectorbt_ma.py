from __future__ import annotations

from pathlib import Path

import pandas as pd

from finharness.vectorbt_runner import run_vectorbt_moving_average_research

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "experiments" / "fixtures" / "sample_prices.csv"


def main() -> None:
    history = pd.read_csv(
        DATA,
        names=["date", "open", "high", "low", "close", "volume"],
    )
    summary = run_vectorbt_moving_average_research(history, fast=5, slow=10)
    print(f"backend={summary.backend}")
    print(f"start_value={summary.start_value:.2f}")
    print(f"end_value={summary.end_value:.2f}")
    print(f"total_return={summary.total_return:.2%}")
    print(f"trade_count={summary.trade_count}")
    print(f"execution_allowed={str(summary.execution_allowed).lower()}")


if __name__ == "__main__":
    main()
