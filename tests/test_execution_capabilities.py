"""Tests for ExecutionCapabilities model."""

from __future__ import annotations

import unittest

from finharness.execution.capabilities import (
    DEFAULT_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
)


class ExecutionCapabilitiesTest(unittest.TestCase):
    """Verify the canonical capability vocabulary."""

    def test_default_frozen(self) -> None:
        """ExecutionCapabilities is frozen — cannot mutate."""
        caps = DEFAULT_EXECUTION_CAPABILITIES
        with self.assertRaises(Exception):
            caps.submit_live_order = True  # type: ignore[misc]

    def test_submit_simulated_order_true(self) -> None:
        """Default capabilities allow simulated submission."""
        self.assertTrue(DEFAULT_EXECUTION_CAPABILITIES.submit_simulated_order)

    def test_submit_live_order_false(self) -> None:
        """Default capabilities disallow live submission."""
        self.assertFalse(DEFAULT_EXECUTION_CAPABILITIES.submit_live_order)

    def test_manage_broker_credentials_false(self) -> None:
        """Default capabilities disallow credential management."""
        self.assertFalse(DEFAULT_EXECUTION_CAPABILITIES.manage_broker_credentials)

    def test_all_values_boolean(self) -> None:
        """Every capability is a boolean."""
        caps = DEFAULT_EXECUTION_CAPABILITIES
        for field_name in [
            "create_order_draft",
            "run_pretrade_check",
            "record_approval",
            "stage_execution_order",
            "submit_simulated_order",
            "submit_live_order",
            "manage_broker_credentials",
        ]:
            self.assertIsInstance(
                getattr(caps, field_name),
                bool,
                f"{field_name} should be bool",
            )
