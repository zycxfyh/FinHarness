"""Constants and literal types for post-trade processing."""

from __future__ import annotations

from typing import Literal

from finharness.market_data import ROOT

POST_TRADE_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "post-trade"
POST_TRADE_RECEIPT_ROOT = ROOT / "data" / "receipts" / "post-trade"

PostTradeStatus = Literal[
    "pending_monitoring",
    "reconciled_filled",
    "reconciled_canceled",
    "reconciled_rejected",
    "partial_fill_exception",
    "staged_no_trade",
    "lineage_failed",
    "needs_human_review",
]
PostTradeExceptionSeverity = Literal["info", "warning", "critical"]
TerminalQuantityStatus = Literal["pending_monitoring", "canceled", "rejected"]
