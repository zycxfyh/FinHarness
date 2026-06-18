"""Ninth-layer paper execution lifecycle governance package.

The package preserves the original ``finharness.execution`` interface while
keeping implementation concerns in smaller modules.
"""

from __future__ import annotations

from finharness.execution._constants import (
    DEFAULT_PAPER_MARKET_ACCESS_LIMIT,
    EXECUTION_NORMALIZED_ROOT,
    EXECUTION_RECEIPT_ROOT,
    NAUTILUS_ORDER_BACKEND,
    NAUTILUS_PAPER_ADAPTER_NAME,
    PAPER_MARKET_ACCESS_CEILING_FIELD,
    ExecutionAdapterMode,
    ExecutionEventType,
    ExecutionStatus,
)
from finharness.execution._util import event, now_utc, write_json
from finharness.execution.adapters import (
    FakePaperExecutionAdapter,
    NautilusPaperExecutionAdapter,
)
from finharness.execution.bundle import (
    build_execution_bundle_from_risk_gate_snapshot,
    build_execution_quality,
    final_status,
    persist_execution_bundle,
    post_trade_handoff,
)
from finharness.execution.controls import (
    collect_execution_events,
    market_access_limit_for_execution_context,
)
from finharness.execution.models import (
    ExecutionAdapter,
    ExecutionBundle,
    ExecutionContext,
    ExecutionEvent,
    ExecutionIntent,
    ExecutionLineage,
    ExecutionOrderRequest,
    ExecutionQuality,
    ExecutionReceipt,
    ExecutionSnapshot,
    ExecutionSourceSpec,
)
from finharness.execution.planning import (
    allowed_decisions,
    authorization_for_execution_context,
    blocked_event,
    build_execution_intents,
    build_order_requests,
    derive_idempotency_key,
    market_access_key_for_order_request,
    stage_events,
)
from finharness.market_access_ledger import record_consumption

__all__ = [
    "DEFAULT_PAPER_MARKET_ACCESS_LIMIT",
    "EXECUTION_NORMALIZED_ROOT",
    "EXECUTION_RECEIPT_ROOT",
    "NAUTILUS_ORDER_BACKEND",
    "NAUTILUS_PAPER_ADAPTER_NAME",
    "PAPER_MARKET_ACCESS_CEILING_FIELD",
    "ExecutionAdapter",
    "ExecutionAdapterMode",
    "ExecutionBundle",
    "ExecutionContext",
    "ExecutionEvent",
    "ExecutionEventType",
    "ExecutionIntent",
    "ExecutionLineage",
    "ExecutionOrderRequest",
    "ExecutionQuality",
    "ExecutionReceipt",
    "ExecutionSnapshot",
    "ExecutionSourceSpec",
    "ExecutionStatus",
    "FakePaperExecutionAdapter",
    "NautilusPaperExecutionAdapter",
    "allowed_decisions",
    "authorization_for_execution_context",
    "blocked_event",
    "build_execution_bundle_from_risk_gate_snapshot",
    "build_execution_intents",
    "build_execution_quality",
    "build_order_requests",
    "collect_execution_events",
    "derive_idempotency_key",
    "event",
    "final_status",
    "market_access_key_for_order_request",
    "market_access_limit_for_execution_context",
    "now_utc",
    "persist_execution_bundle",
    "post_trade_handoff",
    "record_consumption",
    "stage_events",
    "write_json",
]
