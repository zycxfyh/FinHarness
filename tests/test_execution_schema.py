"""Tests for the canonical Execution Kernel schema.

Validates:
- Live-shaped models: BROKER, ORDER, SUBMIT, EXECUTION are all legal.
- Simulated substrate: adapter_kind="simulated", network_enabled=False.
- Full execution lifecycle: draft → check → approve → stage → submit → report.
- No external network connectivity exists.
"""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

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
from finharness.statecore.store import init_state_core, write_records


class ExecutionSchemaTest(unittest.TestCase):
    """Canonical execution schema: models exist and can be persisted."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "db.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    # ── helpers ──────────────────────────────────────────────────────────

    def _broker_id(self, environment: str = "live") -> str:
        c = BrokerConnection(
            broker_connection_id=f"bc_{environment}",
            environment=ExecutionEnvironment(environment),
            broker_name="Simulated Broker",
            adapter_kind="simulated",
            enabled=True,
            network_enabled=False,
        )
        write_records([c], engine=self.engine)
        return c.broker_connection_id

    def _account_id(
        self, broker_id: str, environment: str = "live"
    ) -> str:
        a = ExecutionAccount(
            execution_account_id=f"acct_{environment}",
            broker_connection_id=broker_id,
            environment=ExecutionEnvironment(environment),
            account_label=f"Test {environment} account",
            base_currency="USD",
            funded=False,
        )
        write_records([a], engine=self.engine)
        return a.execution_account_id

    def _draft_id(
        self, account_id: str, environment: str = "live"
    ) -> str:
        d = OrderDraft(
            order_draft_id=f"draft_{environment}",
            environment=ExecutionEnvironment(environment),
            execution_account_id=account_id,
            instrument_ref="SPY",
            symbol="SPY",
            side="buy",
            order_type="market",
            quantity=Decimal("100"),
            time_in_force="day",
            rationale="test order draft",
        )
        write_records([d], engine=self.engine)
        return d.order_draft_id

    # ── tests ────────────────────────────────────────────────────────────

    def test_live_broker_connection_exists(self) -> None:
        """LIVE is a legal environment. Simulated adapter is valid."""
        bid = self._broker_id("live")
        from sqlmodel import Session, select

        with Session(self.engine) as s:
            bc = s.exec(
                select(BrokerConnection).where(
                    BrokerConnection.broker_connection_id == bid
                )
            ).one()
            self.assertEqual(bc.environment, ExecutionEnvironment.LIVE)
            self.assertEqual(bc.adapter_kind, "simulated")
            self.assertTrue(bc.enabled)
            self.assertFalse(bc.network_enabled)

    def test_paper_broker_connection_exists(self) -> None:
        """PAPER is also a legal environment."""
        bid = self._broker_id("paper")
        from sqlmodel import Session, select

        with Session(self.engine) as s:
            bc = s.exec(
                select(BrokerConnection).where(
                    BrokerConnection.broker_connection_id == bid
                )
            ).one()
            self.assertEqual(bc.environment, ExecutionEnvironment.PAPER)

    def test_live_execution_account_unfunded(self) -> None:
        """A live account can exist without being funded."""
        bid = self._broker_id("live")
        aid = self._account_id(bid, "live")
        from sqlmodel import Session, select

        with Session(self.engine) as s:
            acct = s.exec(
                select(ExecutionAccount).where(
                    ExecutionAccount.execution_account_id == aid
                )
            ).one()
            self.assertEqual(acct.environment, ExecutionEnvironment.LIVE)
            self.assertFalse(acct.funded)

    def test_live_order_draft(self) -> None:
        """An order draft with environment='live' is valid."""
        bid = self._broker_id("live")
        aid = self._account_id(bid, "live")
        did = self._draft_id(aid, "live")
        from sqlmodel import Session, select

        with Session(self.engine) as s:
            draft = s.exec(
                select(OrderDraft).where(OrderDraft.order_draft_id == did)
            ).one()
            self.assertEqual(draft.environment, ExecutionEnvironment.LIVE)
            self.assertEqual(draft.side, "buy")
            self.assertEqual(draft.order_type, "market")
            self.assertEqual(draft.quantity, Decimal("100"))
            self.assertEqual(draft.symbol, "SPY")

    def test_full_execution_lifecycle_live(self) -> None:
        """Complete canonical lifecycle: draft → check → approve → stage → report."""
        bid = self._broker_id("live")
        aid = self._account_id(bid, "live")
        did = self._draft_id(aid, "live")

        # Pre-trade check
        check = PreTradeCheck(
            pretrade_check_id="ptc_1",
            order_draft_id=did,
            check_status="pass",
            findings_json='[{"rule":"position_limit","result":"ok"}]',
            required_approval_level="human",
        )
        write_records([check], engine=self.engine)

        # Approval
        approval = ApprovalRecord(
            approval_id="appr_1",
            order_draft_id=did,
            decision="approved",
            reviewer_id="test_operator",
            rationale="within risk limits",
        )
        write_records([approval], engine=self.engine)

        # Stage execution order
        eo = ExecutionOrder(
            execution_order_id="eo_1",
            order_draft_id=did,
            broker_connection_id=bid,
            environment=ExecutionEnvironment.LIVE,
            execution_status="staged",
        )
        write_records([eo], engine=self.engine)

        # Simulated execution report
        report = ExecutionReport(
            execution_report_id="er_1",
            execution_order_id="eo_1",
            report_type="simulated_submit_ack",
            fill_status="none",
            filled_quantity=Decimal("0"),
            broker_event_ref="simulated:eo_1",
        )
        write_records([report], engine=self.engine)

        # Verify all persisted
        from sqlmodel import Session, select

        with Session(self.engine) as s:
            self.assertEqual(
                s.exec(
                    select(PreTradeCheck).where(
                        PreTradeCheck.pretrade_check_id == "ptc_1"
                    )
                ).one().check_status,
                "pass",
            )
            self.assertEqual(
                s.exec(
                    select(ApprovalRecord).where(
                        ApprovalRecord.approval_id == "appr_1"
                    )
                ).one().decision,
                "approved",
            )
            eo_found = s.exec(
                select(ExecutionOrder).where(
                    ExecutionOrder.execution_order_id == "eo_1"
                )
            ).one()
            self.assertEqual(eo_found.environment, ExecutionEnvironment.LIVE)
            self.assertEqual(eo_found.execution_status, "staged")
            self.assertIsNone(eo_found.submitted_at_utc)

    def test_execution_report_simulated_fill(self) -> None:
        """A simulated fill report is valid without network."""
        bid = self._broker_id("live")
        aid = self._account_id(bid, "live")
        did = self._draft_id(aid, "live")

        eo = ExecutionOrder(
            execution_order_id="eo_fill",
            order_draft_id=did,
            broker_connection_id=bid,
            environment=ExecutionEnvironment.LIVE,
            execution_status="staged",
        )
        write_records([eo], engine=self.engine)

        report = ExecutionReport(
            execution_report_id="er_fill",
            execution_order_id="eo_fill",
            report_type="simulated_fill",
            fill_status="filled",
            filled_quantity=Decimal("100"),
            average_fill_price=Decimal("450.25"),
            broker_event_ref="simulated:eo_fill",
        )
        write_records([report], engine=self.engine)

        from sqlmodel import Session, select

        with Session(self.engine) as s:
            r = s.exec(
                select(ExecutionReport).where(
                    ExecutionReport.execution_report_id == "er_fill"
                )
            ).one()
            self.assertEqual(r.fill_status, "filled")
            self.assertEqual(r.filled_quantity, Decimal("100"))
            self.assertEqual(r.average_fill_price, Decimal("450.25"))

    def test_position_delta_after_execution(self) -> None:
        """Position delta tracks position change from execution."""
        bid = self._broker_id("live")
        aid = self._account_id(bid, "live")
        did = self._draft_id(aid, "live")

        eo = ExecutionOrder(
            execution_order_id="eo_pos",
            order_draft_id=did,
            broker_connection_id=bid,
            environment=ExecutionEnvironment.LIVE,
            execution_status="staged",
        )
        er = ExecutionReport(
            execution_report_id="er_pos",
            execution_order_id="eo_pos",
            report_type="simulated_fill",
            fill_status="filled",
            filled_quantity=Decimal("100"),
        )
        write_records([eo, er], engine=self.engine)

        delta = PositionDelta(
            position_delta_id="pd_1",
            execution_report_id="er_pos",
            execution_account_id=aid,
            symbol="SPY",
            delta_quantity=Decimal("100"),
            post_execution_quantity=Decimal("100"),
        )
        write_records([delta], engine=self.engine)

        from sqlmodel import Session, select

        with Session(self.engine) as s:
            d = s.exec(
                select(PositionDelta).where(
                    PositionDelta.position_delta_id == "pd_1"
                )
            ).one()
            self.assertEqual(d.symbol, "SPY")
            self.assertEqual(d.delta_quantity, Decimal("100"))

    def test_reconciliation_report(self) -> None:
        """Reconciliation report tracks expected vs actual positions."""
        bid = self._broker_id("live")
        aid = self._account_id(bid, "live")

        rec = ReconciliationReport(
            reconciliation_id="rec_1",
            execution_account_id=aid,
            reconciliation_status="pending",
            expected_positions_json='[{"symbol":"SPY","qty":100}]',
            actual_positions_json="[]",
            discrepancies_json="[]",
        )
        write_records([rec], engine=self.engine)

        from sqlmodel import Session, select

        with Session(self.engine) as s:
            r = s.exec(
                select(ReconciliationReport).where(
                    ReconciliationReport.reconciliation_id == "rec_1"
                )
            ).one()
            self.assertEqual(r.reconciliation_status, "pending")

    def test_no_network_enabled(self) -> None:
        """Prove that no broker connection has network enabled."""
        self._broker_id("live")
        self._broker_id("paper")
        from sqlmodel import Session, select

        with Session(self.engine) as s:
            conns = s.exec(select(BrokerConnection)).all()
            for c in conns:
                self.assertFalse(
                    c.network_enabled,
                    f"BrokerConnection {c.broker_connection_id} has network enabled",
                )

    def test_live_environment_is_enum_value(self) -> None:
        """LIVE is literally ExecutionEnvironment.LIVE."""
        self.assertEqual(ExecutionEnvironment.LIVE.value, "live")
        self.assertEqual(ExecutionEnvironment.PAPER.value, "paper")
