"""Tests for legacy surface deprecation response headers.

Verifies that legacy ActionIntent and PaperValidation routes
include X-FinHarness-Legacy-Surface and X-FinHarness-Superseded-By
response headers.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.api.app import create_app
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.store import init_state_core
from tests.asgi_test_client import AsgiTestClient


class LegacyRouteHeadersTest(unittest.TestCase):
    """Verify legacy deprecation headers on representative endpoints."""

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
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    # -- Paper validation routes (no seed data needed, lists return empty) --

    def test_paper_accounts_list_returns_legacy_headers(self) -> None:
        """GET /paper-accounts returns legacy surface deprecation headers."""
        response = self.client.get("/paper-accounts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("X-FinHarness-Legacy-Surface"), "true"
        )
        self.assertIn(
            "/execution/order-drafts",
            response.headers.get("X-FinHarness-Superseded-By", ""),
        )

    def test_paper_execution_receipts_list_returns_legacy_headers(self) -> None:
        """GET /paper-execution-receipts returns legacy surface deprecation headers."""
        response = self.client.get("/paper-execution-receipts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("X-FinHarness-Legacy-Surface"), "true"
        )

    def test_paper_order_ticket_candidates_list_returns_legacy_headers(self) -> None:
        """GET /paper-order-ticket-candidates returns legacy surface deprecation headers."""
        response = self.client.get("/paper-order-ticket-candidates")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("X-FinHarness-Legacy-Surface"), "true"
        )
        self.assertIn(
            "/execution/orders/{id}/submit",
            response.headers.get("X-FinHarness-Superseded-By", ""),
        )
