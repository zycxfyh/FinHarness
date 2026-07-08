"""Tests for execution API routes.

Verifies all 8 execution routes: create draft, run check, approve,
stage, submit, read order, list orders, read report.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from finharness.api.app import create_app
from finharness.execution.adapters.simulated_broker import SimulatedBrokerAdapter
from finharness.execution.broker import (
    clear_broker_registry,
    register_broker_adapter,
)
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.execution_models import (
    BrokerConnection,
    ExecutionAccount,
    ExecutionEnvironment,
)
from finharness.statecore.store import init_state_core, write_records
from tests.asgi_test_client import AsgiTestClient


class ExecutionRoutesTest(unittest.TestCase):
    """Execution API route tests."""

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
        self.addCleanup(self.tmp.cleanup)

    def _setup_broker_and_account(self) -> tuple[str, str]:
        bc = BrokerConnection(
            broker_connection_id="bc_test",
            environment=ExecutionEnvironment.LIVE,
            broker_name="Simulated",
            adapter_kind="simulated",
            enabled=True,
            network_enabled=False,
        )
        acct = ExecutionAccount(
            execution_account_id="acct_test",
            broker_connection_id="bc_test",
            environment=ExecutionEnvironment.LIVE,
            account_label="Test",
            funded=False,
        )
        write_records([bc, acct], engine=self.engine)
        register_broker_adapter(
            "bc_test",
            SimulatedBrokerAdapter(
                environment=ExecutionEnvironment.LIVE, simulate_fill=True
            ),
        )
        return "bc_test", "acct_test"

    # ── POST routes ──────────────────────────────────────────────────────

    def test_post_order_draft(self) -> None:
        _, aid = self._setup_broker_and_account()
        resp = self.client.post(
            "/execution/order-drafts",
            json={
                "execution_account_id": aid,
                "instrument_ref": "SPY",
                "symbol": "SPY",
                "side": "sell",
                "order_type": "market",
                "quantity": "100",
                "rationale": "reduce exposure",
                "environment": "live",
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["side"], "sell")
        self.assertEqual(data["symbol"], "SPY")
        self.assertEqual(data["draft_status"], "draft")
        self.assertIsNotNone(data["receipt_ref"])

    def test_post_pretrade_check(self) -> None:
        _, aid = self._setup_broker_and_account()
        draft = self.client.post(
            "/execution/order-drafts",
            json={
                "execution_account_id": aid,
                "instrument_ref": "SPY",
                "symbol": "SPY",
                "side": "buy",
                "order_type": "market",
                "quantity": "50",
                "rationale": "test",
            },
        ).json()

        resp = self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/pretrade-checks",
            json={
                "findings": [{"rule": "ok", "severity": "info", "result": "pass"}],
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["check_status"], "pass")

    def test_post_approval(self) -> None:
        _, aid = self._setup_broker_and_account()
        draft = self.client.post(
            "/execution/order-drafts",
            json={
                "execution_account_id": aid,
                "instrument_ref": "SPY",
                "symbol": "SPY",
                "side": "sell",
                "order_type": "market",
                "quantity": "100",
                "rationale": "test",
            },
        ).json()

        resp = self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/approvals",
            json={
                "decision": "approved",
                "reviewer_id": "test_op",
                "rationale": "go",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["decision"], "approved")

    def test_post_stage(self) -> None:
        bid, aid = self._setup_broker_and_account()
        draft = self.client.post(
            "/execution/order-drafts",
            json={
                "execution_account_id": aid,
                "instrument_ref": "SPY",
                "symbol": "SPY",
                "side": "buy",
                "order_type": "market",
                "quantity": "100",
                "rationale": "test",
            },
        ).json()

        # Pre-conditions required before staging
        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/pretrade-checks",
            json={},
        )
        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/approvals",
            json={"decision": "approved", "reviewer_id": "test_op", "rationale": "go"},
        )

        resp = self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/stage",
            json={"broker_connection_id": bid},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["execution_status"], "staged")

    def test_post_submit(self) -> None:
        bid, aid = self._setup_broker_and_account()
        draft = self.client.post(
            "/execution/order-drafts",
            json={
                "execution_account_id": aid,
                "instrument_ref": "SPY",
                "symbol": "SPY",
                "side": "sell",
                "order_type": "market",
                "quantity": "100",
                "rationale": "test",
            },
        ).json()

        # Pre-conditions required before staging
        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/pretrade-checks",
            json={},
        )
        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/approvals",
            json={"decision": "approved", "reviewer_id": "test_op", "rationale": "go"},
        )

        order = self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/stage",
            json={"broker_connection_id": bid},
        ).json()

        resp = self.client.post(
            f"/execution/orders/{order['execution_order_id']}/submit",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn(data["report_type"], ("simulated_fill", "simulated_submit_ack"))
        self.assertIsNotNone(data["receipt_ref"])

    # ── GET routes ───────────────────────────────────────────────────────

    def test_get_order(self) -> None:
        bid, aid = self._setup_broker_and_account()
        draft = self.client.post(
            "/execution/order-drafts",
            json={
                "execution_account_id": aid,
                "instrument_ref": "SPY",
                "symbol": "SPY",
                "side": "buy",
                "order_type": "market",
                "quantity": "50",
                "rationale": "test",
            },
        ).json()

        # Pre-conditions
        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/pretrade-checks",
            json={},
        )
        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/approvals",
            json={"decision": "approved", "reviewer_id": "test_op", "rationale": "go"},
        )

        order = self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/stage",
            json={"broker_connection_id": bid},
        ).json()

        resp = self.client.get(
            f"/execution/orders/{order['execution_order_id']}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["execution_status"], "staged")

    def test_get_order_404(self) -> None:
        resp = self.client.get("/execution/orders/nonexistent")
        self.assertEqual(resp.status_code, 404)

    def test_list_orders(self) -> None:
        bid, aid = self._setup_broker_and_account()
        draft = self.client.post(
            "/execution/order-drafts",
            json={
                "execution_account_id": aid,
                "instrument_ref": "SPY",
                "symbol": "SPY",
                "side": "buy",
                "order_type": "market",
                "quantity": "10",
                "rationale": "test list",
            },
        ).json()

        # Pre-conditions
        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/pretrade-checks",
            json={},
        )
        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/approvals",
            json={"decision": "approved", "reviewer_id": "test_op", "rationale": "go"},
        )

        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/stage",
            json={"broker_connection_id": bid},
        )

        resp = self.client.get("/execution/orders")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_get_report(self) -> None:
        bid, aid = self._setup_broker_and_account()
        draft = self.client.post(
            "/execution/order-drafts",
            json={
                "execution_account_id": aid,
                "instrument_ref": "SPY",
                "symbol": "SPY",
                "side": "sell",
                "order_type": "market",
                "quantity": "100",
                "rationale": "test",
            },
        ).json()

        # Pre-conditions
        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/pretrade-checks",
            json={},
        )
        self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/approvals",
            json={"decision": "approved", "reviewer_id": "test_op", "rationale": "go"},
        )

        order = self.client.post(
            f"/execution/order-drafts/{draft['order_draft_id']}/stage",
            json={"broker_connection_id": bid},
        ).json()
        report = self.client.post(
            f"/execution/orders/{order['execution_order_id']}/submit",
        ).json()

        resp = self.client.get(
            f"/execution/reports/{report['execution_report_id']}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json()["execution_order_id"], order["execution_order_id"]
        )

    def test_get_report_404(self) -> None:
        resp = self.client.get("/execution/reports/nonexistent")
        self.assertEqual(resp.status_code, 404)
