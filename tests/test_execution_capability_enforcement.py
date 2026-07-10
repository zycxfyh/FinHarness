"""Semantic tests for fail-closed execution capability enforcement."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, select

from finharness.api.app import create_app
from finharness.execution.capabilities import (
    DEFAULT_EXECUTION_CAPABILITIES,
    ExecutionCapabilities,
    ExecutionCapabilityDeniedError,
)
from finharness.execution.commands import submit_order
from finharness.execution.services import (
    create_order_draft,
    record_approval,
    run_pretrade_check,
    stage_execution_order,
)
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.execution_models import (
    ApprovalRecord,
    BrokerConnection,
    ExecutionAccount,
    ExecutionOrder,
    ExecutionReport,
    OrderDraft,
    PreTradeCheck,
)
from finharness.statecore.models import ReceiptIndex
from finharness.statecore.store import init_state_core, write_records
from tests.asgi_test_client import AsgiTestClient


class ExecutionCapabilityEnforcementTest(unittest.TestCase):
    """Disabled capabilities deny before state, receipt, or adapter effects."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state.sqlite")
        self.receipt_root = self.root / "receipts" / "execution"
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self._setup_broker_and_account()

    def _setup_broker_and_account(self) -> None:
        connection = BrokerConnection(
            broker_connection_id="bc_capability",
            environment="live",
            broker_name="Simulated",
            adapter_kind="simulated",
            network_enabled=False,
            credential_ref=None,
        )
        account = ExecutionAccount(
            execution_account_id="ea_capability",
            broker_connection_id=connection.broker_connection_id,
            environment="live",
            account_label="capability test",
            base_currency="USD",
            funded=False,
        )
        write_records([connection, account], engine=self.engine)

    def _disabled(self, flag: str) -> ExecutionCapabilities:
        return replace(DEFAULT_EXECUTION_CAPABILITIES, **{flag: False})

    def _state_counts(self) -> tuple[int, ...]:
        models = (
            OrderDraft,
            PreTradeCheck,
            ApprovalRecord,
            ExecutionOrder,
            ExecutionReport,
            ReceiptIndex,
        )
        with Session(self.engine) as session:
            return tuple(len(session.exec(select(model)).all()) for model in models)

    def _receipt_files(self) -> tuple[Path, ...]:
        if not self.receipt_root.exists():
            return ()
        return tuple(sorted(self.receipt_root.rglob("*.json")))

    def _create_draft(self) -> OrderDraft:
        return create_order_draft(
            engine=self.engine,
            receipt_root=self.receipt_root,
            execution_account_id="ea_capability",
            instrument_ref="SPY",
            symbol="SPY",
            side="buy",
            order_type="market",
            quantity=Decimal("10"),
            rationale="capability test",
            environment="live",
        )

    def _create_approved_draft(self) -> OrderDraft:
        draft = self._create_draft()
        run_pretrade_check(
            engine=self.engine,
            receipt_root=self.receipt_root,
            order_draft_id=draft.order_draft_id,
        )
        record_approval(
            engine=self.engine,
            receipt_root=self.receipt_root,
            order_draft_id=draft.order_draft_id,
            decision="approved",
            reviewer_id="human-reviewer",
            rationale="approved for simulated test",
        )
        return draft

    def _create_staged_order(self) -> ExecutionOrder:
        draft = self._create_approved_draft()
        return stage_execution_order(
            engine=self.engine,
            receipt_root=self.receipt_root,
            order_draft_id=draft.order_draft_id,
            broker_connection_id="bc_capability",
        )

    def _assert_denial(self, capability: str, callback) -> None:
        before_state = self._state_counts()
        before_files = self._receipt_files()
        with self.assertRaises(ExecutionCapabilityDeniedError) as raised:
            callback()
        self.assertEqual(raised.exception.capability, capability)
        self.assertEqual(self._state_counts(), before_state)
        self.assertEqual(self._receipt_files(), before_files)

    def test_create_order_draft_denied_before_writes(self) -> None:
        self._assert_denial(
            "create_order_draft",
            lambda: create_order_draft(
                engine=self.engine,
                receipt_root=self.receipt_root,
                execution_account_id="ea_capability",
                instrument_ref="SPY",
                symbol="SPY",
                side="buy",
                order_type="market",
                quantity=Decimal("10"),
                rationale="must be denied",
                capabilities=self._disabled("create_order_draft"),
            ),
        )

    def test_pretrade_check_denied_without_draft_mutation(self) -> None:
        draft = self._create_draft()
        self._assert_denial(
            "run_pretrade_check",
            lambda: run_pretrade_check(
                engine=self.engine,
                receipt_root=self.receipt_root,
                order_draft_id=draft.order_draft_id,
                capabilities=self._disabled("run_pretrade_check"),
            ),
        )
        with Session(self.engine) as session:
            persisted = session.get(OrderDraft, draft.order_draft_id)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.draft_status, "draft")

    def test_approval_denied_without_draft_mutation(self) -> None:
        draft = self._create_draft()
        self._assert_denial(
            "record_approval",
            lambda: record_approval(
                engine=self.engine,
                receipt_root=self.receipt_root,
                order_draft_id=draft.order_draft_id,
                decision="approved",
                reviewer_id="human-reviewer",
                rationale="must be denied",
                capabilities=self._disabled("record_approval"),
            ),
        )
        with Session(self.engine) as session:
            persisted = session.get(OrderDraft, draft.order_draft_id)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.draft_status, "draft")

    def test_stage_denied_without_draft_mutation(self) -> None:
        draft = self._create_approved_draft()
        self._assert_denial(
            "stage_execution_order",
            lambda: stage_execution_order(
                engine=self.engine,
                receipt_root=self.receipt_root,
                order_draft_id=draft.order_draft_id,
                broker_connection_id="bc_capability",
                capabilities=self._disabled("stage_execution_order"),
            ),
        )
        with Session(self.engine) as session:
            persisted = session.get(OrderDraft, draft.order_draft_id)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.draft_status, "approved")

    def test_submit_denied_before_adapter_resolution_or_writes(self) -> None:
        order = self._create_staged_order()
        with patch("finharness.execution.commands.resolve_broker_adapter") as resolve:
            self._assert_denial(
                "submit_simulated_order",
                lambda: submit_order(
                    engine=self.engine,
                    receipt_root=self.receipt_root,
                    execution_order_id=order.execution_order_id,
                    capabilities=self._disabled("submit_simulated_order"),
                ),
            )
        resolve.assert_not_called()
        with Session(self.engine) as session:
            persisted = session.get(ExecutionOrder, order.execution_order_id)
            self.assertIsNotNone(persisted)
            self.assertEqual(persisted.execution_status, "staged")

    def test_api_injects_capabilities_and_returns_stable_403(self) -> None:
        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
            execution_capabilities=self._disabled("create_order_draft"),
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)
        before_state = self._state_counts()
        before_files = self._receipt_files()

        response = client.post(
            "/execution/order-drafts",
            json={
                "execution_account_id": "ea_capability",
                "instrument_ref": "SPY",
                "symbol": "SPY",
                "side": "buy",
                "order_type": "market",
                "quantity": "10",
                "rationale": "must be denied",
                "environment": "live",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json(),
            {
                "detail": {
                    "code": "execution_capability_denied",
                    "capability": "create_order_draft",
                    "message": "Execution capability is disabled: create_order_draft",
                }
            },
        )
        self.assertEqual(self._state_counts(), before_state)
        self.assertEqual(self._receipt_files(), before_files)


if __name__ == "__main__":
    unittest.main()
