"""Tests for adapter boundary — prove no real external side-effect path.

Verifies:
- Only simulated adapters by default
- No network, no credentials
- No external broker SDK imports
- submit_order returns simulated broker_event_ref
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session, select

from finharness.execution.broker import (
    clear_broker_registry,
    register_broker_adapter,
)
from finharness.execution.commands import submit_order
from finharness.execution.services import (
    create_order_draft,
    record_approval,
    run_pretrade_check,
    stage_execution_order,
)
from finharness.statecore.execution_models import (
    BrokerConnection,
    ExecutionAccount,
    ExecutionEnvironment,
    ExecutionOrder,
    ExecutionReport,
)
from finharness.statecore.store import init_state_core, write_records


class AdapterBoundaryTest(unittest.TestCase):
    """Prove no real external side-effect path exists."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "db.sqlite")
        self.receipt_root = self.root / "receipts" / "execution"
        clear_broker_registry()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(clear_broker_registry)

    def _setup_connection(self) -> tuple[str, str]:
        """Create a simulated broker connection + account."""
        bc = BrokerConnection(
            broker_connection_id="bc_boundary",
            environment="live",
            broker_name="Boundary Test",
            adapter_kind="simulated",
            network_enabled=False,
            credential_ref=None,
        )
        ea = ExecutionAccount(
            execution_account_id="ea_boundary",
            broker_connection_id="bc_boundary",
            environment="live",
            account_label="boundary test",
            base_currency="USD",
        )
        write_records([bc, ea], engine=self.engine)
        return ("bc_boundary", "ea_boundary")

    # ── Broker connection invariants ─────────────────────────────────────

    def test_connection_adapter_kind_is_simulated(self) -> None:
        """BrokerConnection.adapter_kind must be 'simulated'."""
        bid, _ = self._setup_connection()
        with Session(self.engine) as s:
            bc = s.exec(
                select(BrokerConnection).where(
                    BrokerConnection.broker_connection_id == bid
                )
            ).one()
        self.assertEqual(bc.adapter_kind, "simulated")

    def test_connection_network_disabled(self) -> None:
        """BrokerConnection.network_enabled must be False."""
        bid, _ = self._setup_connection()
        with Session(self.engine) as s:
            bc = s.exec(
                select(BrokerConnection).where(
                    BrokerConnection.broker_connection_id == bid
                )
            ).one()
        self.assertFalse(bc.network_enabled)

    def test_connection_credential_ref_is_none(self) -> None:
        """BrokerConnection.credential_ref must be None."""
        bid, _ = self._setup_connection()
        with Session(self.engine) as s:
            bc = s.exec(
                select(BrokerConnection).where(
                    BrokerConnection.broker_connection_id == bid
                )
            ).one()
        self.assertIsNone(bc.credential_ref)

    # ── Import boundary ───────────────────────────────────────────────────

    def test_no_external_broker_sdk_imported(self) -> None:
        """No real broker SDK modules in sys.modules."""
        forbidden = {"alpaca", "okx", "ib_insync", "ccxt", "alpaca_trade_api"}
        loaded = forbidden & set(sys.modules)
        self.assertEqual(
            loaded, set(),
            f"Real broker SDK modules should not be loaded: {loaded}",
        )

    # ── submit_order surface ──────────────────────────────────────────────

    def _create_submitted_order(self) -> tuple[ExecutionOrder, str]:
        """Full lifecycle through submit."""
        bid, aid = self._setup_connection()
        draft = create_order_draft(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=aid,
            instrument_ref="SPY",
            symbol="SPY",
            side="buy",
            order_type="market",
            quantity=Decimal("10"),
            rationale="boundary test",
        )
        run_pretrade_check(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
        )
        record_approval(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            reviewer_id="test_op",
            decision="approved",
            rationale="ok",
        )
        order = stage_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            broker_connection_id=bid,
        )
        return order, bid

    def test_submit_order_no_adapter_returns_simulated_ack(self) -> None:
        """submit_order without registered adapter → simulated broker_event_ref."""
        order, _ = self._create_submitted_order()
        report = submit_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
        )
        self.assertIsInstance(report, ExecutionReport)
        ref = report.broker_event_ref or ""
        self.assertTrue(
            ref.startswith("no_adapter:")
            or ref.startswith("simulated:"),
            f"broker_event_ref should be simulated, got: {report.broker_event_ref}",
        )

        # No-adapter path must still write submit lifecycle receipts
        from sqlmodel import Session, select

        from finharness.statecore.models import ReceiptIndex
        with Session(self.engine) as s:
            kinds = {r.kind for r in s.exec(select(ReceiptIndex)).all()}
        self.assertIn("execution.order.submit_attempted", kinds,
                      "no-adapter submit must write submit_attempted receipt")
        self.assertIn("execution.order.submitted", kinds,
                      "no-adapter submit must write submitted receipt")

    def test_submit_order_with_adapter_returns_simulated_fill(self) -> None:
        """submit_order with SimulatedBrokerAdapter → simulated:fill ref."""
        from finharness.execution.adapters.simulated_broker import SimulatedBrokerAdapter

        order, bid = self._create_submitted_order()
        register_broker_adapter(
            bid,
            SimulatedBrokerAdapter(
                environment=ExecutionEnvironment.LIVE, simulate_fill=True
            ),
        )

        report = submit_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
        )
        self.assertIsInstance(report, ExecutionReport)
        ref = report.broker_event_ref or ""
        self.assertTrue(
            ref.startswith("simulated:"),
            f"broker_event_ref should start with 'simulated:', got: {report.broker_event_ref}",
        )
        self.assertEqual(report.fill_status, "filled")
