"""Paper execution adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import (
    ClientOrderId,
    InstrumentId,
    StrategyId,
    TraderId,
)
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.model.orders import LimitOrder, MarketOrder

from finharness.execution._constants import (
    NAUTILUS_ORDER_BACKEND,
    NAUTILUS_PAPER_ADAPTER_NAME,
    ExecutionAdapterMode,
)
from finharness.execution._util import event
from finharness.execution.models import ExecutionEvent, ExecutionOrderRequest


class FakePaperExecutionAdapter:
    """Deterministic paper adapter; never talks to a real broker."""

    adapter_name = "fake_paper_adapter"
    adapter_mode: ExecutionAdapterMode = "paper"

    def __init__(self, *, fill_mode: Literal["accepted", "partial", "filled", "reject"]):
        self.fill_mode = fill_mode
        self.submitted_keys: set[str] = set()

    def submit(self, request: ExecutionOrderRequest) -> list[ExecutionEvent]:
        if request.idempotency_key in self.submitted_keys:
            return [
                event(
                    event_type="rejected",
                    status="rejected",
                    order_request_id=request.order_request_id,
                    raw_status="duplicate_client_order_id",
                    raw_event={"idempotency_key": request.idempotency_key},
                )
            ]
        self.submitted_keys.add(request.idempotency_key)
        submitted = event(
            event_type="submitted",
            status="submitted_paper",
            order_request_id=request.order_request_id,
            quantity=request.quantity,
            raw_status="submitted_paper",
            raw_event={"client_order_id": request.client_order_id},
        )
        if self.fill_mode == "reject":
            return [
                submitted,
                event(
                    event_type="rejected",
                    status="rejected",
                    order_request_id=request.order_request_id,
                    quantity=request.quantity,
                    raw_status="rejected",
                    raw_event={"reason": "fake adapter configured rejection"},
                ),
            ]
        if self.fill_mode == "partial":
            return [
                submitted,
                event(
                    event_type="partial_fill",
                    status="partially_filled",
                    order_request_id=request.order_request_id,
                    quantity=request.quantity,
                    filled_quantity=max(1, request.quantity // 2),
                    average_price=request.reference_price,
                    raw_status="partially_filled",
                    raw_event={"fill_mode": self.fill_mode},
                ),
            ]
        if self.fill_mode == "filled":
            return [
                submitted,
                event(
                    event_type="fill",
                    status="filled",
                    order_request_id=request.order_request_id,
                    quantity=request.quantity,
                    filled_quantity=request.quantity,
                    average_price=request.reference_price,
                    raw_status="filled",
                    raw_event={"fill_mode": self.fill_mode},
                ),
            ]
        return [
            submitted,
            event(
                event_type="accepted",
                status="accepted",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="accepted",
                raw_event={"fill_mode": self.fill_mode},
            ),
        ]

    def cancel(self, request: ExecutionOrderRequest) -> list[ExecutionEvent]:
        return [
            event(
                event_type="cancel_requested",
                status="cancel_requested",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="pending_cancel",
                raw_event={"client_order_id": request.client_order_id},
            ),
            event(
                event_type="canceled",
                status="canceled",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="canceled",
                raw_event={"client_order_id": request.client_order_id},
            ),
        ]


class NautilusPaperExecutionAdapter:
    """Paper adapter that delegates order-shape semantics to NautilusTrader.

    It does not route to a broker, simulate fills, or authorize live execution.
    The adapter only converts a FinHarness order request into a Nautilus typed
    order and records the resulting order evidence.
    """

    adapter_name = NAUTILUS_PAPER_ADAPTER_NAME
    adapter_mode: ExecutionAdapterMode = "paper"

    def __init__(
        self,
        *,
        trader_id: str = "FINHARNESS-001",
        strategy_id: str = "L9-PAPER",
        venue: str = "FINHARNESS",
    ) -> None:
        self.trader_id = TraderId(trader_id)
        self.strategy_id = StrategyId(strategy_id)
        self.venue = venue

    def submit(self, request: ExecutionOrderRequest) -> list[ExecutionEvent]:
        order = self._build_order(request)
        raw_order = order.to_dict()
        return [
            event(
                event_type="submitted",
                status="submitted_paper",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="nautilus_order_initialized",
                raw_event={
                    "backend": NAUTILUS_ORDER_BACKEND,
                    "adapter_name": self.adapter_name,
                    "order": raw_order,
                },
            ),
            event(
                event_type="accepted",
                status="accepted",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="nautilus_paper_accepted",
                raw_event={
                    "backend": NAUTILUS_ORDER_BACKEND,
                    "adapter_name": self.adapter_name,
                    "order_type": raw_order.get("type"),
                    "order_status": raw_order.get("status"),
                    "client_order_id": raw_order.get("client_order_id"),
                    "execution_allowed": False,
                },
            ),
        ]

    def cancel(self, request: ExecutionOrderRequest) -> list[ExecutionEvent]:
        return [
            event(
                event_type="cancel_requested",
                status="cancel_requested",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="nautilus_paper_cancel_requested",
                raw_event={
                    "backend": NAUTILUS_ORDER_BACKEND,
                    "adapter_name": self.adapter_name,
                    "client_order_id": request.client_order_id,
                },
            ),
            event(
                event_type="canceled",
                status="canceled",
                order_request_id=request.order_request_id,
                quantity=request.quantity,
                raw_status="nautilus_paper_canceled",
                raw_event={
                    "backend": NAUTILUS_ORDER_BACKEND,
                    "adapter_name": self.adapter_name,
                    "client_order_id": request.client_order_id,
                },
            ),
        ]

    def _build_order(self, request: ExecutionOrderRequest) -> MarketOrder | LimitOrder:
        instrument_id = InstrumentId.from_str(f"{request.symbol}.{self.venue}")
        client_order_id = ClientOrderId(request.client_order_id)
        order_side = OrderSide.BUY if request.side == "buy" else OrderSide.SELL
        time_in_force = TimeInForce.DAY if request.time_in_force == "day" else TimeInForce.GTC
        quantity = Quantity.from_int(request.quantity)
        common = {
            "trader_id": self.trader_id,
            "strategy_id": self.strategy_id,
            "instrument_id": instrument_id,
            "client_order_id": client_order_id,
            "order_side": order_side,
            "quantity": quantity,
            "init_id": UUID4(),
            "ts_init": int(datetime.now(UTC).timestamp() * 1_000_000_000),
            "time_in_force": time_in_force,
        }
        if request.order_type == "limit":
            return LimitOrder(
                **common,
                price=Price.from_str(f"{request.reference_price:.8f}"),
            )
        return MarketOrder(**common)
