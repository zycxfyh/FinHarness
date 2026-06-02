"""Optional CCXT source adapter.

CCXT is the intended crypto venue breadth wheel, but it is not currently a
project dependency. This module provides the governance boundary without
installing or reimplementing CCXT.
"""

from __future__ import annotations

import importlib
from typing import Any

from finharness.market_data import SourceSpec, package_version


def require_ccxt() -> Any:
    try:
        return importlib.import_module("ccxt")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "ccxt is not installed; add it explicitly before enabling crypto venue ingestion"
        ) from exc


def build_ccxt_source_spec(exchange_id: str, dataset: str) -> SourceSpec:
    return SourceSpec(
        provider=f"ccxt:{exchange_id}",
        upstream_source=exchange_id,
        asset_class="crypto",
        dataset=dataset,
        access_method="api_pull",
        wheel="ccxt",
        wheel_version=package_version("ccxt"),
    )


def load_ccxt_markets(exchange_id: str) -> dict[str, Any]:
    """Load exchange market metadata through CCXT when the wheel is installed."""
    ccxt = require_ccxt()
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True})
    return exchange.load_markets()
