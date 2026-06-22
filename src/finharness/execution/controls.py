"""Pre-submit market-access controls for paper execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from finharness.effective_ceilings import CeilingResolutionError, EnforcedCap, enforce_request_limit
from finharness.execution._constants import (
    DEFAULT_PAPER_MARKET_ACCESS_LIMIT,
    PAPER_MARKET_ACCESS_CEILING_FIELD,
)
from finharness.execution.adapters import NautilusPaperExecutionAdapter
from finharness.execution.models import (
    ExecutionAdapter,
    ExecutionContext,
    ExecutionEvent,
    ExecutionOrderRequest,
)
from finharness.execution.planning import (
    blocked_event,
    market_access_key_for_order_request,
    stage_events,
)
from finharness.market_access_ledger import (
    MarketAccessLedgerError,
    MarketAccessLimit,
    evaluate_market_access,
    load_market_access_ledger,
)


def _record_consumption(**kwargs: Any) -> Any:
    from finharness import execution as execution_package

    return execution_package.record_consumption(**kwargs)


def market_access_limit_for_execution_context(
    context: ExecutionContext,
) -> tuple[MarketAccessLimit, EnforcedCap]:
    requested_notional = (
        context.market_access_limit.max_window_notional
        if context.market_access_limit is not None
        else None
    )
    cap = enforce_request_limit(
        field=PAPER_MARKET_ACCESS_CEILING_FIELD,
        default_ceiling=DEFAULT_PAPER_MARKET_ACCESS_LIMIT.max_window_notional,
        request_limit=requested_notional,
        rule_change_root=Path(context.market_access_ceiling_rule_root)
        if context.market_access_ceiling_rule_root
        else None,
        certification_root=Path(context.market_access_ceiling_certification_root)
        if context.market_access_ceiling_certification_root
        else None,
    )
    requested_count = (
        context.market_access_limit.max_window_order_count
        if context.market_access_limit is not None
        else DEFAULT_PAPER_MARKET_ACCESS_LIMIT.max_window_order_count
    )
    return (
        MarketAccessLimit(
            max_window_notional=cap.enforced_cap,
            max_window_order_count=min(
                requested_count,
                DEFAULT_PAPER_MARKET_ACCESS_LIMIT.max_window_order_count,
            ),
        ),
        cap,
    )


def collect_execution_events(
    *,
    context: ExecutionContext,
    order_requests: list[ExecutionOrderRequest],
    adapter: ExecutionAdapter | None = None,
) -> list[ExecutionEvent]:
    if not order_requests:
        return []
    events = stage_events(order_requests)
    if not context.operator_execute or context.requested_mode == "dry_run":
        return events
    if context.requested_mode == "live":
        events.append(blocked_event("live execution is blocked in Layer 9 MVP"))
        return events
    paper_adapter = adapter or NautilusPaperExecutionAdapter()
    for request in order_requests:
        notional = request.quantity * request.reference_price
        try:
            effective_market_access_limit, market_access_cap = (
                market_access_limit_for_execution_context(context)
            )
        except CeilingResolutionError as exc:
            events.append(
                blocked_event(
                    "market-access notional ceiling could not be resolved; "
                    f"refusing fail-closed: {exc}"
                )
            )
            continue
        try:
            market_access = evaluate_market_access(
                key=market_access_key_for_order_request(
                    context=context,
                    request=request,
                ),
                notional=notional,
                limit=effective_market_access_limit,
                ledger=load_market_access_ledger(),
                limit_evidence=market_access_cap.as_receipt_dict(),
            )
        except MarketAccessLedgerError as exc:
            events.append(
                blocked_event(
                    "market-access ledger unreadable; refusing fail-closed: "
                    f"{exc}"
                )
            )
            continue
        if not market_access.allowed_within_limit:
            events.append(
                blocked_event(
                    "market-access ledger blocked order request: "
                    + "; ".join(market_access.blocking_reasons)
                )
            )
            continue
        try:
            _record_consumption(
                key=market_access_key_for_order_request(
                    context=context,
                    request=request,
                ),
                notional=notional,
                limit=effective_market_access_limit,
                limit_evidence=market_access_cap.as_receipt_dict(),
                source_ref=request.order_request_id,
            )
        except MarketAccessLedgerError as exc:
            events.append(
                blocked_event(
                    "market-access ledger consumption failed before paper submit: "
                    f"{exc}"
                )
            )
            continue
        events.extend(paper_adapter.submit(request))
        if context.cancel_after_submit:
            events.extend(paper_adapter.cancel(request))
    return events
