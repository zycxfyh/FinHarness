"""Constants and public literal types for execution."""

from __future__ import annotations

from typing import Literal

from finharness.market_access_ledger import MarketAccessLimit
from finharness.market_data import ROOT

EXECUTION_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "executions"
EXECUTION_RECEIPT_ROOT = ROOT / "data" / "receipts" / "executions"
NAUTILUS_ORDER_BACKEND = "NautilusTrader.model.orders"
NAUTILUS_PAPER_ADAPTER_NAME = "nautilus_paper_order_adapter"
DEFAULT_PAPER_MARKET_ACCESS_LIMIT = MarketAccessLimit(
    max_window_notional=1000.0,
    max_window_order_count=20,
)
PAPER_MARKET_ACCESS_CEILING_FIELD = "paper_market_access_window_notional"

ExecutionAdapterMode = Literal["dry_run", "paper", "live"]
ExecutionStatus = Literal[
    "not_submitted",
    "staged",
    "submitted_paper",
    "accepted",
    "partially_filled",
    "filled",
    "cancel_requested",
    "canceled",
    "rejected",
    "blocked_before_submit",
    "reconciled",
]
ExecutionEventType = Literal[
    "staged",
    "submitted",
    "accepted",
    "partial_fill",
    "fill",
    "cancel_requested",
    "canceled",
    "rejected",
    "blocked",
    "reconciled",
]
