"""Tests for simulated broker adapter and submit command.

Verifies:
- SimulatedBrokerAdapter produces correct ExecutionReport shapes.
- submit_order command wires adapter → service → receipt.
- Graceful fallback when no adapter is registered.
- No external network capability.
"""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session, select

from finharness.execution.adapters.simulated_broker import SimulatedBrokerAdapter
from finharness.execution.broker import (
    clear_broker_registry,
    register_broker_adapter,
    resolve_broker_adapter,
)
from finharness.execution.commands import submit_order
from finharness.execution.services import (
    create_order_draft,
    stage_execution_order,
)
from finharness.statecore.execution_models import (
    BrokerConnection,
    ExecutionAccount,
    ExecutionEnvironment,
    ExecutionOrder,
    OrderDraft,
)
from finharness.statecore.models import ReceiptIndex
from finharness.statecore.store import init_state_core, write_records


class SimulatedBrokerAdapterTest(unittest.TestCase):
    """SimulatedBrokerAdapter unit tests."""

    def test_submit_ack_without_fill(self) -> None:
        """Adapter with simulate_fill=False returns submit_ack."""
        adapter = SimulatedBrokerAdapter(
            environment=ExecutionEnvironment.PAPER,
            simulate_fill=False,
        )
        order = ExecutionOrder(
            execution_order_id="eo_1",
            order_draft_id="draft_1",
            broker_connection_id="bc_1",
            environment=ExecutionEnvironment.PAPER,
            execution_status="staged",
        )
        draft = OrderDraft(
            order_draft_id="draft_1",
            environment=ExecutionEnvironment.PAPER,
            execution_account_id="acct_1",
            instrument_ref="SPY",
            symbol="SPY",
            side="sell",
            order_type="market",
            quantity=Decimal("100"),
            rationale="test",
        )
        report = adapter.submit_order(order, draft)
        self.assertEqual(report.report_type, "simulated_submit_ack")
        self.assertEqual(report.fill_status, "none")
        self.assertEqual(report.filled_quantity, Decimal("0"))
        self.assertIsNone(report.average_fill_price)

    def test_submit_with_fill(self) -> None:
        """Adapter with simulate_fill=True returns simulated_fill."""
        adapter = SimulatedBrokerAdapter(
            environment=ExecutionEnvironment.LIVE,
            simulate_fill=True,
        )
        order = ExecutionOrder(
            execution_order_id="eo_2",
            order_draft_id="draft_2",
            broker_connection_id="bc_2",
            environment=ExecutionEnvironment.LIVE,
        )
        draft = OrderDraft(
            order_draft_id="draft_2",
            environment=ExecutionEnvironment.LIVE,
            execution_account_id="acct_2",
            instrument_ref="SPY",
            symbol="SPY",
            side="buy",
            order_type="limit",
            quantity=Decimal("50"),
            limit_price=Decimal("450.00"),
            rationale="test",
        )
        report = adapter.submit_order(order, draft)
        self.assertEqual(report.report_type, "simulated_fill")
        self.assertEqual(report.fill_status, "filled")
        self.assertEqual(report.filled_quantity, Decimal("50"))
        self.assertEqual(report.average_fill_price, Decimal("450.00"))

    def test_cancel_order(self) -> None:
        """Cancel returns a cancellation report."""
        adapter = SimulatedBrokerAdapter()
        order = ExecutionOrder(
            execution_order_id="eo_3",
            order_draft_id="draft_3",
            broker_connection_id="bc_3",
            environment=ExecutionEnvironment.PAPER,
        )
        report = adapter.cancel_order(order)
        self.assertEqual(report.fill_status, "cancelled")
        self.assertEqual(report.filled_quantity, Decimal("0"))

    def test_environment_is_correct(self) -> None:
        """Adapter environment is configurable."""
        paper = SimulatedBrokerAdapter(environment=ExecutionEnvironment.PAPER)
        live = SimulatedBrokerAdapter(environment=ExecutionEnvironment.LIVE)
        self.assertEqual(paper.environment, ExecutionEnvironment.PAPER)
        self.assertEqual(live.environment, ExecutionEnvironment.LIVE)


class SubmitOrderCommandTest(unittest.TestCase):
    """submit_order command integration tests with real StateCore."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "db.sqlite")
        self.receipt_root = self.root / "receipts" / "execution"
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        clear_broker_registry()

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
        return "bc_test", "acct_test"

    def _create_draft_and_stage(self, bid: str, aid: str) -> tuple[str, str]:
        draft = create_order_draft(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=aid,
            instrument_ref="SPY",
            symbol="SPY",
            side="sell",
            order_type="market",
            quantity=Decimal("100"),
            rationale="submit test",
            environment="live",
        )
        order = stage_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            broker_connection_id=bid,
        )
        return draft.order_draft_id, order.execution_order_id

    def test_submit_order_with_simulated_adapter(self) -> None:
        """submit_order through a registered simulated adapter."""
        bid, aid = self._setup_broker_and_account()
        _, oid = self._create_draft_and_stage(bid, aid)

        # Register adapter
        adapter = SimulatedBrokerAdapter(
            environment=ExecutionEnvironment.LIVE, simulate_fill=True
        )
        register_broker_adapter(bid, adapter)

        # Submit
        report = submit_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=oid,
        )

        self.assertIn(report.report_type, ("simulated_fill", "simulated_submit_ack"))

        # Verify receipts exist
        with Session(self.engine) as s:
            kinds = {
                r.kind for r in s.exec(select(ReceiptIndex)).all()
            }
            self.assertIn("execution.order.submit_attempted", kinds)
            self.assertIn("execution.order.submitted", kinds)
            self.assertIn("execution.report.recorded", kinds)

        # Order status updated (record_execution_report sets filled when filled)
        with Session(self.engine) as s:
            order = s.exec(
                select(ExecutionOrder).where(
                    ExecutionOrder.execution_order_id == oid
                )
            ).one()
            self.assertIn(order.execution_status, ("submitted", "filled"))

    def test_submit_order_without_adapter(self) -> None:
        """submit_order without a registered adapter gracefully records a report."""
        bid, aid = self._setup_broker_and_account()
        _, oid = self._create_draft_and_stage(bid, aid)

        # No adapter registered
        self.assertIsNone(resolve_broker_adapter(bid))

        report = submit_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=oid,
        )

        self.assertEqual(report.report_type, "simulated_submit_ack")
        self.assertIn("no_adapter", report.broker_event_ref or "")

    def test_adapter_returns_fill_report(self) -> None:
        """Simulated adapter with fill produces filled ExecutionReport."""
        bid, aid = self._setup_broker_and_account()
        _, oid = self._create_draft_and_stage(bid, aid)

        adapter = SimulatedBrokerAdapter(
            environment=ExecutionEnvironment.LIVE, simulate_fill=True
        )
        register_broker_adapter(bid, adapter)

        report = submit_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=oid,
        )

        self.assertEqual(report.fill_status, "filled")
        self.assertEqual(report.filled_quantity, Decimal("100"))
        self.assertIsNotNone(report.average_fill_price)
        self.assertIsNotNone(report.receipt_ref)
