from __future__ import annotations

import numpy as np
import pandas as pd

from finharness.portfolio_risk import optimize_riskfolio_allocation


def main() -> None:
    rng = np.random.default_rng(20260614)
    returns = pd.DataFrame(
        {
            "SPY": rng.normal(0.0005, 0.010, size=120),
            "QQQ": rng.normal(0.0007, 0.014, size=120),
            "TLT": rng.normal(0.0002, 0.006, size=120),
        }
    )
    summary = optimize_riskfolio_allocation(returns, concentration_cap=0.7)
    print(f"backend={summary.backend}")
    print(f"weight_sum={summary.weight_sum:.6f}")
    print(f"max_weight={summary.max_weight:.6f}")
    print(f"concentration_ok={str(summary.concentration_ok).lower()}")
    print(f"execution_allowed={str(summary.execution_allowed).lower()}")


if __name__ == "__main__":
    main()
