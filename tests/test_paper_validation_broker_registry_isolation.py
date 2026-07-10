"""Broker registry runtime isolation tests for paper validation surface.

SEC-02C: Prove that PaperValidation's real runtime path does not
register, query, or submit to any broker adapter.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness.api.app import create_app
from finharness.execution.broker import (
    _broker_registry,
    clear_broker_registry,
    register_broker_adapter,
)
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.store import init_state_core
from tests.asgi_test_client import AsgiTestClient


class PaperValidationBrokerRegistryIsolationTest(unittest.TestCase):
    """Real paper validation golden path must not touch broker registry."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "db.sqlite")
        self.receipt_root = self.root / "receipts" / "state-core"
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
        )
        self.client = AsgiTestClient(self.app)
        clear_broker_registry()
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(clear_broker_registry)
        self.addCleanup(self.tmp.cleanup)

    # ── Golden path runner ───────────────────────────────────────────────

    def _run_paper_golden_path(self) -> str:
        """Run paper account creation + listing + positions query.

        Returns the created paper_account_id.
        """
        # Create paper account
        resp = self.client.post("/paper-accounts", json={
            "display_name": "Isolation Test",
            "starting_cash": "100000",
        })
        self.assertEqual(resp.status_code, 200)
        account_id = resp.json()["paper_account"]["paper_account_id"]

        # List paper accounts
        resp = self.client.get("/paper-accounts")
        self.assertEqual(resp.status_code, 200)

        # Get single paper account
        resp = self.client.get(f"/paper-accounts/{account_id}")
        self.assertEqual(resp.status_code, 200)

        # Query paper positions
        resp = self.client.get(f"/paper-accounts/{account_id}/positions")
        self.assertEqual(resp.status_code, 200)

        # List paper order ticket candidates (empty)
        resp = self.client.get("/paper-order-ticket-candidates")
        self.assertEqual(resp.status_code, 200)

        # List paper execution receipts (empty)
        resp = self.client.get("/paper-execution-receipts")
        self.assertEqual(resp.status_code, 200)

        return account_id

    # ── Positive tests: isolation holds ─────────────────────────────────

    def test_broker_registry_is_empty_at_start(self) -> None:
        """Broker registry starts empty."""
        self.assertEqual(len(_broker_registry), 0)

    def test_paper_golden_path_never_registers_broker_adapter(self) -> None:
        """Running paper golden path never calls register_broker_adapter."""
        with patch(
            "finharness.execution.broker.register_broker_adapter"
        ) as mock_register:
            self._run_paper_golden_path()
            mock_register.assert_not_called()

    def test_paper_golden_path_never_resolves_broker_adapter(self) -> None:
        """Running paper golden path never calls resolve_broker_adapter."""
        with patch(
            "finharness.execution.broker.resolve_broker_adapter"
        ) as mock_resolve:
            self._run_paper_golden_path()
            mock_resolve.assert_not_called()

    def test_paper_golden_path_never_calls_submit_order(self) -> None:
        """Running paper golden path never calls submit_order."""
        with patch(
            "finharness.execution.commands.submit_order"
        ) as mock_submit:
            self._run_paper_golden_path()
            mock_submit.assert_not_called()

    def test_paper_golden_path_keeps_registry_empty(self) -> None:
        """Broker registry remains empty after full paper golden path."""
        self._run_paper_golden_path()
        self.assertEqual(
            len(_broker_registry), 0,
            "Broker registry must remain empty after paper operations"
        )

    # ── Negative test: live adapter rejected ─────────────────────────────

    def test_registering_live_adapter_raises_value_error(self) -> None:
        """Registering a non-simulated adapter raises ValueError."""

        class FakeLiveAdapter:
            adapter_kind = "live"
            environment = "live"

        with self.assertRaises(ValueError) as ctx:
            register_broker_adapter("fake-live", FakeLiveAdapter())
        self.assertIn("simulated", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
