"""H3: a real, deterministic disconfirming check for the validation layer.

The MVP event-reaction check only recorded whether market inputs existed; the
B-doc named this as the toy that keeps validation from disconfirming anything.
This module computes a real realized-move metric over a price series and returns
a verdict that can WEAKEN a hypothesis when the predicted reaction did not show
up in the data. It deliberately never returns "supported": a realized move does
not prove the hypothesis's mechanism, so the strongest honest verdict here is
"inconclusive" (a move happened, causation unattributed). This keeps validation
disconfirming-capable without overclaiming.

Adopt-not-invent: the return/drawdown math comes from finharness.metrics
(summarize), not a reimplementation.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from finharness.market_data import ROOT
from finharness.metrics import summarize

# A realized absolute total return below this floor over the window means the
# predicted reaction did not materialize — evidence that weakens the hypothesis.
DEFAULT_MOVE_FLOOR = 0.01


def load_cached_close_series(symbol: str, *, cache_dir: Path | None = None) -> list[float] | None:
    """Read the close series from data/cache/<symbol>_history.csv.

    Returns None when no cache exists for the symbol (a normal state before
    task workflow:daily-evidence has run); callers degrade gracefully.
    """
    base = cache_dir or (ROOT / "data" / "cache")
    path = base / f"{symbol.lower()}_history.csv"
    if not path.is_file():
        return None
    closes: list[float] = []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                value = row.get("close")
                if value in (None, ""):
                    continue
                try:
                    closes.append(float(value))
                except (TypeError, ValueError):
                    continue
    except OSError:
        return None
    return closes or None


def assess_realized_move(
    prices: list[float], *, move_floor: float = DEFAULT_MOVE_FLOOR
) -> dict[str, Any]:
    """Compute a real realized-move verdict over a price series.

    verdict:
      not_testable  fewer than two prices
      weakened      |total_return| < move_floor (predicted reaction absent)
      inconclusive  a material move occurred (not attributed to the hypothesis)
    """
    if len(prices) < 2:
        return {
            "testable": False,
            "verdict": "not_testable",
            "metrics": {"price_count": len(prices)},
        }
    summary = summarize(prices)
    moved = abs(summary.total_return) >= move_floor
    return {
        "testable": True,
        "verdict": "inconclusive" if moved else "weakened",
        "weakens": not moved,
        "metrics": {
            "price_count": len(prices),
            "total_return": summary.total_return,
            "max_drawdown": summary.max_drawdown,
            "annualized_volatility": summary.annualized_volatility,
            "move_floor": move_floor,
        },
    }
