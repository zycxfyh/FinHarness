"""Tests for adapter registration policy — simulated-only enforcement."""

from __future__ import annotations

import unittest

from finharness.execution.adapters.simulated_broker import SimulatedBrokerAdapter
from finharness.execution.broker import (
    clear_broker_registry,
    register_broker_adapter,
)


class FakeLiveAdapter:
    """A fake adapter with adapter_kind='live' — should be rejected."""
    environment = "live"
    adapter_kind = "live"


class FakeNoKindAdapter:
    """A fake adapter with no adapter_kind — should be rejected."""
    environment = "live"


class AdapterRegistrationPolicyTest(unittest.TestCase):
    """Prove only simulated adapters can be registered."""

    def setUp(self) -> None:
        clear_broker_registry()
        self.addCleanup(clear_broker_registry)

    def test_register_simulated_adapter_succeeds(self) -> None:
        """SimulatedBrokerAdapter registration succeeds."""
        adapter = SimulatedBrokerAdapter()
        register_broker_adapter("bc_test", adapter)
        self.assertEqual(adapter.adapter_kind, "simulated")

    def test_register_fake_live_adapter_raises(self) -> None:
        """Adapter with adapter_kind='live' raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            register_broker_adapter("bc_test", FakeLiveAdapter())
        self.assertIn("simulated", str(ctx.exception).lower())

    def test_register_adapter_missing_kind_raises(self) -> None:
        """Adapter with no adapter_kind raises ValueError."""
        with self.assertRaises(ValueError):
            register_broker_adapter("bc_test", FakeNoKindAdapter())
