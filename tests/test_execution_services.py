"""Tests for execution services — full lifecycle on simulated substrate.

Proves the canonical execution lifecycle runs end-to-end:
draft → check → approve → stage → submit → report → position delta → reconciliation.
"""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from sqlmodel import Session, select

from finharness.execution.receipts import EXECUTION_RECEIPT_KINDS
from finharness.execution.services import (
    create_order_draft,
    record_approval,
    record_execution_report,
    record_position_delta,
    record_reconciliation,
    run_pretrade_check,
    stage_execution_order,
    submit_execution_order,
)
from finharness.statecore.execution_models import (
    ApprovalRecord,
    BrokerConnection,
    ExecutionAccount,
    ExecutionEnvironment,
    ExecutionOrder,
    ExecutionReport,
    OrderDraft,
    PositionDelta,
    PreTradeCheck,
    ReconciliationReport,
)
from finharness.statecore.models import ReceiptIndex
from finharness.statecore.store import init_state_core, write_records


class ExecutionServicesTest(unittest.TestCase):
    """Full execution lifecycle on simulated substrate."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "db.sqlite")
        self.receipt_root = self.root / "receipts" / "execution"
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _setup_broker_and_account(self) -> tuple[str, str]:
        """Create a live simulated broker + unfunded account."""
        bc = BrokerConnection(
            broker_connection_id="bc_test",
            environment=ExecutionEnvironment.LIVE,
            broker_name="Test Simulated Broker",
            adapter_kind="simulated",
            enabled=True,
            network_enabled=False,
        )
        acct = ExecutionAccount(
            execution_account_id="acct_test",
            broker_connection_id="bc_test",
            environment=ExecutionEnvironment.LIVE,
            account_label="Test Live Account",
            base_currency="USD",
            funded=False,
        )
        write_records([bc, acct], engine=self.engine)
        return "bc_test", "acct_test"

    # ── tests ────────────────────────────────────────────────────────────

    def test_create_order_draft(self) -> None:
        """Create a live order draft."""
        _, aid = self._setup_broker_and_account()

        draft = create_order_draft(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=aid,
            instrument_ref="SPY",
            symbol="SPY",
            side="sell",
            order_type="market",
            quantity=Decimal("100"),
            rationale="reduce exposure",
            environment="live",
        )

        self.assertEqual(draft.side, "sell")
        self.assertEqual(draft.symbol, "SPY")
        self.assertEqual(draft.quantity, Decimal("100"))
        self.assertEqual(draft.environment, ExecutionEnvironment.LIVE)
        self.assertEqual(draft.draft_status, "draft")
        self.assertIsNotNone(draft.receipt_ref)

        # Receipt was written
        with Session(self.engine) as s:
            idx = s.exec(
                select(ReceiptIndex).where(
                    ReceiptIndex.kind == "execution.order_draft.created"
                )
            ).all()
            self.assertGreaterEqual(len(idx), 1)

    def test_pretrade_check_pass(self) -> None:
        """Pre-trade check passes with no blocking findings."""
        _, aid = self._setup_broker_and_account()
        draft = create_order_draft(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=aid,
            instrument_ref="SPY",
            symbol="SPY",
            side="buy",
            order_type="limit",
            quantity=Decimal("50"),
            limit_price=Decimal("450.00"),
            rationale="test",
        )

        check = run_pretrade_check(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            findings=[
                {"rule": "position_limit", "severity": "info", "result": "ok"},
                {"rule": "margin_check", "severity": "info", "result": "ok"},
            ],
        )

        self.assertEqual(check.check_status, "pass")
        self.assertIsNotNone(check.receipt_ref)

        # Draft status updated
        with Session(self.engine) as s:
            d = s.exec(
                select(OrderDraft).where(OrderDraft.order_draft_id == draft.order_draft_id)
            ).one()
            self.assertEqual(d.draft_status, "pretrade_check_passed")

    def test_pretrade_check_block(self) -> None:
        """Pre-trade check blocks on severity=block finding."""
        _, aid = self._setup_broker_and_account()
        draft = create_order_draft(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=aid,
            instrument_ref="SPY",
            symbol="SPY",
            side="buy",
            order_type="market",
            quantity=Decimal("10000"),
            rationale="oversized test",
        )

        check = run_pretrade_check(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            findings=[
                {"rule": "position_limit", "severity": "block", "result": "exceeds max"},
            ],
        )

        self.assertEqual(check.check_status, "block")
        with Session(self.engine) as s:
            d = s.exec(
                select(OrderDraft).where(OrderDraft.order_draft_id == draft.order_draft_id)
            ).one()
            self.assertEqual(d.draft_status, "pretrade_check_blocked")

    def test_approval(self) -> None:
        """Record an approval decision."""
        _, aid = self._setup_broker_and_account()
        draft = create_order_draft(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=aid,
            instrument_ref="SPY",
            symbol="SPY",
            side="sell",
            order_type="market",
            quantity=Decimal("100"),
            rationale="test",
        )

        approval = record_approval(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            decision="approved",
            reviewer_id="test_operator",
            rationale="within risk limits",
        )

        self.assertEqual(approval.decision, "approved")
        self.assertIsNotNone(approval.receipt_ref)

        with Session(self.engine) as s:
            d = s.exec(
                select(OrderDraft).where(OrderDraft.order_draft_id == draft.order_draft_id)
            ).one()
            self.assertEqual(d.draft_status, "approved")

    def test_stage_execution_order(self) -> None:
        """Stage an execution order from an approved draft."""
        bid, aid = self._setup_broker_and_account()
        draft = create_order_draft(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=aid,
            instrument_ref="SPY",
            symbol="SPY",
            side="buy",
            order_type="market",
            quantity=Decimal("100"),
            rationale="test",
        )

        order = stage_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            broker_connection_id=bid,
        )

        self.assertEqual(order.execution_status, "staged")
        self.assertEqual(order.broker_connection_id, bid)
        self.assertEqual(order.environment, ExecutionEnvironment.LIVE)
        self.assertIsNotNone(order.receipt_ref)

        with Session(self.engine) as s:
            d = s.exec(
                select(OrderDraft).where(OrderDraft.order_draft_id == draft.order_draft_id)
            ).one()
            self.assertEqual(d.draft_status, "staged")

    def test_submit_execution_order(self) -> None:
        """Submit an execution order — no external network."""
        bid, aid = self._setup_broker_and_account()
        draft = create_order_draft(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=aid,
            instrument_ref="SPY",
            symbol="SPY",
            side="sell",
            order_type="market",
            quantity=Decimal("100"),
            rationale="test",
        )
        order = stage_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            broker_connection_id=bid,
        )

        submitted = submit_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
            broker_connection_id=bid,
        )

        self.assertEqual(submitted.execution_status, "submitted")
        self.assertIsNotNone(submitted.submitted_at_utc)
        self.assertIsNotNone(submitted.receipt_ref)

        # Receipt persisted to database
        with Session(self.engine) as s:
            persisted = s.exec(
                select(ExecutionOrder).where(
                    ExecutionOrder.execution_order_id == submitted.execution_order_id
                )
            ).one()
            self.assertEqual(persisted.receipt_ref, submitted.receipt_ref)

        # submit_attempted receipt in index
        with Session(self.engine) as s:
            kinds = {r.kind for r in s.exec(select(ReceiptIndex)).all()}
            self.assertIn("execution.order.submit_attempted", kinds)
            self.assertIn("execution.order.submitted", kinds)

    def test_full_lifecycle(self) -> None:
        """Complete lifecycle: draft → check → approve → stage → submit → report → delta → reconciliation."""
        bid, aid = self._setup_broker_and_account()

        # 1. Draft
        draft = create_order_draft(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=aid,
            instrument_ref="SPY",
            symbol="SPY",
            side="sell",
            order_type="market",
            quantity=Decimal("100"),
            rationale="end-to-end test",
            environment="live",
        )
        self.assertIsNotNone(draft.receipt_ref)

        # 2. Pre-trade check
        check = run_pretrade_check(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            findings=[{"rule": "sizing", "severity": "info", "result": "ok"}],
        )
        self.assertEqual(check.check_status, "pass")

        # 3. Approval
        approval = record_approval(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            decision="approved",
            reviewer_id="test_operator",
            rationale="go",
        )
        self.assertEqual(approval.decision, "approved")

        # 4. Stage
        order = stage_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            order_draft_id=draft.order_draft_id,
            broker_connection_id=bid,
        )
        self.assertEqual(order.execution_status, "staged")

        # 5. Submit
        submitted = submit_execution_order(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
            broker_connection_id=bid,
        )
        self.assertEqual(submitted.execution_status, "submitted")
        self.assertIsNotNone(submitted.receipt_ref)

        # Verify receipt_ref persisted to database
        with Session(self.engine) as s:
            persisted = s.exec(
                select(ExecutionOrder).where(
                    ExecutionOrder.execution_order_id == submitted.execution_order_id
                )
            ).one()
            self.assertEqual(persisted.receipt_ref, submitted.receipt_ref)
            self.assertIsNotNone(persisted.submitted_at_utc)

        # 6. Execution report (simulated)
        report = record_execution_report(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_order_id=order.execution_order_id,
            report_type="simulated_fill",
            fill_status="filled",
            filled_quantity=Decimal("100"),
            average_fill_price=Decimal("450.25"),
            broker_event_ref="simulated:test",
        )
        self.assertEqual(report.fill_status, "filled")
        self.assertIsNotNone(report.receipt_ref)

        # 7. Position delta
        delta = record_position_delta(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_report_id=report.execution_report_id,
            execution_account_id=aid,
            symbol="SPY",
            delta_quantity=Decimal("-100"),
            post_execution_quantity=Decimal("0"),
        )
        self.assertEqual(delta.symbol, "SPY")
        self.assertIsNotNone(delta.receipt_ref)

        # 8. Reconciliation
        rec = record_reconciliation(
            engine=self.engine,
            receipt_root=str(self.receipt_root),
            execution_account_id=aid,
            expected_positions=[{"symbol": "SPY", "qty": 0}],
            actual_positions=[{"symbol": "SPY", "qty": 0}],
            discrepancies=[],
        )
        self.assertEqual(rec.reconciliation_status, "matched")

        # Verify all receipts in index
        with Session(self.engine) as s:
            all_receipts = s.exec(select(ReceiptIndex)).all()
            kinds = {r.kind for r in all_receipts}
            for k in [
                "execution.order_draft.created",
                "execution.pretrade_check.recorded",
                "execution.approval.recorded",
                "execution.order.staged",
                "execution.order.submit_attempted",
                "execution.order.submitted",
                "execution.report.recorded",
                "execution.position_delta.recorded",
                "execution.reconciliation.recorded",
            ]:
                self.assertIn(k, kinds, f"Missing receipt kind: {k}")

    def test_receipt_kinds_defined(self) -> None:
        """All 9 receipt kinds are defined."""
        self.assertEqual(len(EXECUTION_RECEIPT_KINDS), 9)
        expected = {
            "execution.order_draft.created",
            "execution.pretrade_check.recorded",
            "execution.approval.recorded",
            "execution.order.staged",
            "execution.order.submit_attempted",
            "execution.order.submitted",
            "execution.report.recorded",
            "execution.position_delta.recorded",
            "execution.reconciliation.recorded",
        }
        self.assertEqual(set(EXECUTION_RECEIPT_KINDS), expected)

    def test_broker_connection_has_no_network(self) -> None:
        """Prove the test broker has no network capability."""
        bid, _ = self._setup_broker_and_account()
        with Session(self.engine) as s:
            bc = s.exec(
                select(BrokerConnection).where(
                    BrokerConnection.broker_connection_id == bid
                )
            ).one()
            self.assertFalse(bc.network_enabled)
            self.assertEqual(bc.adapter_kind, "simulated")
