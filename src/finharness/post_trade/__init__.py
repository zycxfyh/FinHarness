"""Tenth-layer post-trade reconciliation and review governance package.

The package preserves the original ``finharness.post_trade`` interface while
keeping implementation concerns in smaller modules.
"""

from __future__ import annotations

from finharness.post_trade._constants import (
    POST_TRADE_NORMALIZED_ROOT,
    POST_TRADE_RECEIPT_ROOT,
    PostTradeExceptionSeverity,
    PostTradeStatus,
    TerminalQuantityStatus,
)
from finharness.post_trade._util import exception, now_utc, write_json
from finharness.post_trade.bundle import (
    accounting_handoff,
    build_post_trade_bundle_from_execution_snapshot,
    build_post_trade_quality,
    performance_handoff,
    persist_post_trade_bundle,
    portfolio_handoff,
    post_trade_storage_roots,
)
from finharness.post_trade.costs import (
    average_fill_price,
    build_cost_estimates,
    implementation_shortfall,
)
from finharness.post_trade.exceptions import build_post_trade_exceptions
from finharness.post_trade.models import (
    PostTradeBundle,
    PostTradeContext,
    PostTradeCostEstimate,
    PostTradeException,
    PostTradeLineage,
    PostTradeQuality,
    PostTradeReceipt,
    PostTradeReconciliation,
    PostTradeSnapshot,
    PostTradeSourceSpec,
)
from finharness.post_trade.reconciliation import (
    build_reconciliations,
    events_by_order,
    final_post_trade_status,
    lifecycle_notes,
    status_for_events,
    submitted_quantity_for_events,
    terminal_quantity_for_events,
)

__all__ = [
    "POST_TRADE_NORMALIZED_ROOT",
    "POST_TRADE_RECEIPT_ROOT",
    "PostTradeBundle",
    "PostTradeContext",
    "PostTradeCostEstimate",
    "PostTradeException",
    "PostTradeExceptionSeverity",
    "PostTradeLineage",
    "PostTradeQuality",
    "PostTradeReceipt",
    "PostTradeReconciliation",
    "PostTradeSnapshot",
    "PostTradeSourceSpec",
    "PostTradeStatus",
    "TerminalQuantityStatus",
    "accounting_handoff",
    "average_fill_price",
    "build_cost_estimates",
    "build_post_trade_bundle_from_execution_snapshot",
    "build_post_trade_exceptions",
    "build_post_trade_quality",
    "build_reconciliations",
    "events_by_order",
    "exception",
    "final_post_trade_status",
    "implementation_shortfall",
    "lifecycle_notes",
    "now_utc",
    "performance_handoff",
    "persist_post_trade_bundle",
    "portfolio_handoff",
    "post_trade_storage_roots",
    "status_for_events",
    "submitted_quantity_for_events",
    "terminal_quantity_for_events",
    "write_json",
]
