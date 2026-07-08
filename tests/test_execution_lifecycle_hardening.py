"""Tests for execution lifecycle hardening — illegal state transitions.

Verifies the canonical execution lifecycle prevents:
- staging rejected/cancelled drafts
- staging without PreTradeCheck or ApprovalRecord
- submitting already-submitted (terminal) orders
- partial fill integrity
"""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session, select

from finharness.execution.services import (
    create_order_draft,
    record_approval,
    record_execution_report,
    run_pretrade_check,
    stage_execution_order,
    submit_execution_order,
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


class ExecutionLifecycleHardeningTest(unittest.TestCase):
    """Test that illegal state transitions are rejected."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "db.sqlite")
        self.receipt_root = self.root / "receipts" / "execution"
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _setup_broker_and_account(self) -> tuple[str, str]:
        bc = BrokerConnection(
            broker_connection_id="bc_test",
            environment="live",
            broker_name="Test Broker",
            adapter_kind="simulated",
            network_enabled=False,
            credential_ref=None,
        )
        ea = ExecutionAccount(
            execution_account_id="ea_test",
            broker_connection_id="bc_test",
            environment="live",
            account_label="test",
            base_currency="USD",
        )
        write_records([bc, ea], engine=self.engine)
        return ("bc_test", "ea_test")

    def _create_draft(self) -> OrderDraft:
        bc_id, ea_id = self._setup_broker_and_account()
        return create_order_draft(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=ea_id,
            instrument_ref="SPY",
            symbol="SPY",
            side="buy",
            order_type="market",
            quantity=Decimal("10"),
            rationale="test draft",
        )

    # ── Stage rejection tests ────────────────────────────────────────────

    def test_cannot_stage_rejected_draft(self) -> None:
        """Rejected draft → stage should fail."""
        draft = self._create_draft()
        with Session(self.engine) as s:
            d = s.exec(
                select(OrderDraft).where(OrderDraft.order_draft_id == draft.order_draft_id)
            ).one()
            d.draft_status = "rejected"
            s.add(d)
            s.commit()

        with self.assertRaises(ValueError) as ctx:
            stage_execution_order(
                engine=self.engine,
                receipt_root=str(self.receipt_root),
                order_draft_id=draft.order_draft_id,
                broker_connection_id="bc_test",
            )
        self.assertIn("rejected", str(ctx.exception).lower())

    def test_cannot_stage_cancelled_draft(self) -> None:
        """Cancelled draft → stage should fail."""
        draft = self._create_draft()
        with Session(self.engine) as s:
            d = s.exec(
                select(OrderDraft).where(OrderDraft.order_draft_id == draft.order_draft_id)
            ).one()
            d.draft_status = "cancelled"
            s.add(d)
            s.commit()

        with self.assertRaises(ValueError):
            stage_execution_order(
                engine=self.engine,
                receipt_root=str(self.receipt_root),
                order_draft_id=draft.order_draft_id,
                broker_connection_id="bc_test",
            )

    def test_cannot_stage_without_pretrade_check(self) -> None:
        """Draft without PreTradeCheck → stage should fail."""
        draft = self._create_draft()

        with self.assertRaises(ValueError) as ctx:
            stage_execution_order(
                engine=self.engine,
                receipt_root=str(self.receipt_root),
                order_draft_id=draft.order_draft_id,
                broker_connection_id="bc_test",
            )
        self.assertIn("pretrade", str(ctx.exception).lower())

    def test_cannot_stage_without_approval(self) -> None:
        """Draft with PreTradeCheck but no Approval → stage should fail."""
        draft = self._create_draft()
        run_pretrade_check(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
        )

        with self.assertRaises(ValueError) as ctx:
            stage_execution_order(
                engine=self.engine,
                receipt_root=str(self.receipt_root),
                order_draft_id=draft.order_draft_id,
                broker_connection_id="bc_test",
            )
        self.assertIn("approval", str(ctx.exception).lower())

    # ── Submit guard tests ────────────────────────────────────────────────

    def _create_staged_order(self) -> ExecutionOrder:
        """Full happy path: draft → check → approve → stage."""
        draft = self._create_draft()
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
            rationale="looks good",
        )
        order = stage_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            broker_connection_id="bc_test",
        )
        return order

    def test_cannot_submit_already_submitted_order(self) -> None:
        """Already-submitted order → second submit should fail."""
        order = self._create_staged_order()
        submit_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
            broker_connection_id="bc_test",
        )

        with self.assertRaises(ValueError) as ctx:
            submit_execution_order(
                engine=self.engine,
                receipt_root=str(self.receipt_root),
                execution_order_id=order.execution_order_id,
                broker_connection_id="bc_test",
            )
        self.assertIn("submitted", str(ctx.exception).lower())

    def test_submit_creates_attempted_then_submitted_receipts(self) -> None:
        """submit_execution_order writes submit_attempted, then submitted receipts."""
        order = self._create_staged_order()
        submit_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
            broker_connection_id="bc_test",
        )

        with Session(self.engine) as s:
            indexes = s.exec(
                select(ReceiptIndex).where(
                    ReceiptIndex.refs.contains(order.execution_order_id)
                )
            ).all()

        kinds = {idx.kind for idx in indexes}
        self.assertIn("execution.order.submit_attempted", kinds)
        self.assertIn("execution.order.submitted", kinds)

    # ── Fill integrity ────────────────────────────────────────────────────

    def test_partial_fill_does_not_mark_filled(self) -> None:
        """Partial fill → status partial_fill, not filled."""
        order = self._create_staged_order()
        submit_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
            broker_connection_id="bc_test",
        )

        report = record_execution_report(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
            report_type="fill",
            fill_status="partial",
            filled_quantity=Decimal("5"),
            average_fill_price=Decimal("450.00"),
        )
        self.assertEqual(report.fill_status, "partial")

        with Session(self.engine) as s:
            persisted = s.exec(
                select(ExecutionOrder).where(
                    ExecutionOrder.execution_order_id == order.execution_order_id
                )
            ).one()
        self.assertEqual(persisted.execution_status, "partial_fill")

    def test_full_fill_marks_order_filled(self) -> None:
        """Full fill → order.execution_status = filled."""
        order = self._create_staged_order()
        submit_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
            broker_connection_id="bc_test",
        )

        record_execution_report(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
            report_type="fill",
            fill_status="filled",
            filled_quantity=Decimal("10"),
            average_fill_price=Decimal("450.00"),
        )

        with Session(self.engine) as s:
            persisted = s.exec(
                select(ExecutionOrder).where(
                    ExecutionOrder.execution_order_id == order.execution_order_id
                )
            ).one()
        self.assertEqual(persisted.execution_status, "filled")
