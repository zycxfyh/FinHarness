"""Broker adapter protocol and registry.

Defines the BrokerAdapter interface that every broker integration
must implement. The registry maps broker connections to adapter
instances. Only SimulatedBrokerAdapter is registered by default
— no real external broker connectivity exists.
"""

from __future__ import annotations

from typing import Protocol

from finharness.statecore.execution_models import (
    BrokerConnection,
    ExecutionEnvironment,
    ExecutionOrder,
    ExecutionReport,
    OrderDraft,
)


class BrokerAdapter(Protocol):
    """Protocol for broker adapters — paper, simulated, or live.

    Every adapter must declare its environment. Simulated adapters
    return synthetic ExecutionReports. Live adapters would connect
    to real broker APIs — but no live adapter is currently registered.
    """

    environment: ExecutionEnvironment

    def submit_order(
        self, order: ExecutionOrder, draft: OrderDraft
    ) -> ExecutionReport:
        """Submit an order and return an execution report."""
        ...

    def cancel_order(
        self, order: ExecutionOrder
    ) -> ExecutionReport | None:
        """Cancel an order and return a cancellation report, or None if
        cancellation is not supported."""
        ...


# ── Registry ────────────────────────────────────────────────────────────────

_broker_registry: dict[str, BrokerAdapter] = {}


def register_broker_adapter(
    broker_connection_id: str,
    adapter: BrokerAdapter,
) -> None:
    """Register an adapter for a broker connection."""
    _broker_registry[broker_connection_id] = adapter


def resolve_broker_adapter(
    broker_connection_id: str,
) -> BrokerAdapter | None:
    """Resolve a registered adapter, or None if none exists."""
    return _broker_registry.get(broker_connection_id)


def clear_broker_registry() -> None:
    """Clear all registered adapters. For test isolation only."""
    _broker_registry.clear()
