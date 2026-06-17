from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness import execution, post_trade
from finharness.execution import (
    FakePaperExecutionAdapter,
    build_execution_bundle_from_risk_gate_snapshot,
)
from finharness.post_trade import build_post_trade_bundle_from_execution_snapshot
from finharness.post_trade_graph import post_trade_graph, run_post_trade_graph
from tests.test_execution import build_sample_risk_gate_bundle


class PostTradeLayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.env_patch = patch.dict(
            os.environ,
            {
                "FINHARNESS_MARKET_ACCESS_LEDGER_PATH": str(root / "ledger.json"),
                "FINHARNESS_MARKET_ACCESS_RECEIPT_ROOT": str(root / "receipts"),
            },
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_filled_execution_reconciles_and_estimates_cost(self) -> None:
        risk_bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            risk_bundle.snapshot,
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
                "requested_quantity": 2,
                "reference_price": 100.0,
            },
            adapter=FakePaperExecutionAdapter(fill_mode="filled"),
        )
        bundle = build_post_trade_bundle_from_execution_snapshot(
            execution_bundle.snapshot,
            context={"estimated_fee_per_share": 0.01},
        )

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertEqual(bundle.snapshot.final_status, "reconciled_filled")
        self.assertEqual(
            {item.status for item in bundle.snapshot.reconciliations},
            {"reconciled_filled"},
        )
        self.assertTrue(
            all(item.filled_quantity == 2 for item in bundle.snapshot.reconciliations)
        )
        self.assertTrue(
            all(item.intended_quantity == 2 for item in bundle.snapshot.reconciliations)
        )
        self.assertTrue(
            all(item.submitted_quantity == 2 for item in bundle.snapshot.reconciliations)
        )
        self.assertTrue(
            all(item.lifecycle_quantity_reconciled for item in bundle.snapshot.reconciliations)
        )
        self.assertTrue(
            all(item.inputs_disclosed for item in bundle.snapshot.cost_estimates)
        )
        self.assertTrue(
            all(item.arrival_price == 100.0 for item in bundle.snapshot.cost_estimates)
        )
        self.assertTrue(
            all(item.execution_price == 100.0 for item in bundle.snapshot.cost_estimates)
        )
        self.assertTrue(
            all(item.implementation_shortfall == 0.0 for item in bundle.snapshot.cost_estimates)
        )
        self.assertTrue(bundle.snapshot.portfolio_handoff)
        self.assertFalse(bundle.snapshot.order_creation_allowed)

    def test_implementation_shortfall_is_side_aware_for_buy_and_sell(self) -> None:
        risk_bundle = build_sample_risk_gate_bundle()
        buy_execution = build_execution_bundle_from_risk_gate_snapshot(
            risk_bundle.snapshot,
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
                "requested_quantity": 2,
                "reference_price": 100.0,
            },
            adapter=FakePaperExecutionAdapter(fill_mode="filled"),
        )
        buy_events = [
            event.model_copy(update={"average_price": 101.0})
            if event.filled_quantity > 0
            else event
            for event in buy_execution.snapshot.events
        ]
        buy_snapshot = buy_execution.snapshot.model_copy(update={"events": buy_events})
        buy_bundle = build_post_trade_bundle_from_execution_snapshot(buy_snapshot)

        self.assertTrue(
            all(item.side == "buy" for item in buy_bundle.snapshot.cost_estimates)
        )
        self.assertTrue(
            all(item.implementation_shortfall == 2.0 for item in buy_bundle.snapshot.cost_estimates)
        )

        sell_requests = [
            request.model_copy(update={"side": "sell"})
            for request in buy_execution.snapshot.order_requests
        ]
        sell_events = [
            event.model_copy(update={"average_price": 99.0})
            if event.filled_quantity > 0
            else event
            for event in buy_execution.snapshot.events
        ]
        sell_snapshot = buy_execution.snapshot.model_copy(
            update={"order_requests": sell_requests, "events": sell_events}
        )
        sell_bundle = build_post_trade_bundle_from_execution_snapshot(sell_snapshot)

        self.assertTrue(
            all(item.side == "sell" for item in sell_bundle.snapshot.cost_estimates)
        )
        self.assertTrue(
            all(
                item.implementation_shortfall == 2.0
                for item in sell_bundle.snapshot.cost_estimates
            )
        )

    def test_partial_fill_stays_exception_with_remaining_quantity(self) -> None:
        risk_bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            risk_bundle.snapshot,
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
                "requested_quantity": 4,
            },
            adapter=FakePaperExecutionAdapter(fill_mode="partial"),
        )
        bundle = build_post_trade_bundle_from_execution_snapshot(execution_bundle.snapshot)

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertEqual(bundle.snapshot.final_status, "partial_fill_exception")
        self.assertTrue(
            all(item.remaining_quantity == 2 for item in bundle.snapshot.reconciliations)
        )
        self.assertTrue(
            all(item.filled_quantity == 2 for item in bundle.snapshot.reconciliations)
        )
        self.assertTrue(
            all(item.canceled_quantity == 0 for item in bundle.snapshot.reconciliations)
        )
        self.assertTrue(
            all(item.rejected_quantity == 0 for item in bundle.snapshot.reconciliations)
        )
        self.assertTrue(
            all(item.lifecycle_quantity_reconciled for item in bundle.snapshot.reconciliations)
        )
        self.assertIn(
            "partial_fill",
            {item.exception_type for item in bundle.snapshot.exceptions},
        )

    def test_canceled_execution_reconciles_as_canceled(self) -> None:
        risk_bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            risk_bundle.snapshot,
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
                "cancel_after_submit": True,
            },
            adapter=FakePaperExecutionAdapter(fill_mode="accepted"),
        )
        bundle = build_post_trade_bundle_from_execution_snapshot(execution_bundle.snapshot)

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertEqual(bundle.snapshot.final_status, "reconciled_canceled")
        self.assertTrue(
            all(
                item.canceled_quantity == item.intended_quantity
                for item in bundle.snapshot.reconciliations
            )
        )
        self.assertIn(
            "execution_canceled",
            {item.exception_type for item in bundle.snapshot.exceptions},
        )
        self.assertFalse(bundle.snapshot.portfolio_handoff)

    def test_rejected_execution_reconciles_as_rejected(self) -> None:
        risk_bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            risk_bundle.snapshot,
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
            },
            adapter=FakePaperExecutionAdapter(fill_mode="reject"),
        )
        bundle = build_post_trade_bundle_from_execution_snapshot(execution_bundle.snapshot)

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertEqual(bundle.snapshot.final_status, "reconciled_rejected")
        self.assertTrue(
            all(
                item.rejected_quantity == item.intended_quantity
                for item in bundle.snapshot.reconciliations
            )
        )
        self.assertIn(
            "execution_rejected",
            {item.exception_type for item in bundle.snapshot.exceptions},
        )

    def test_missing_arrival_price_records_undisclosed_tca_input(self) -> None:
        risk_bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            risk_bundle.snapshot,
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
                "requested_quantity": 2,
                "reference_price": 100.0,
            },
            adapter=FakePaperExecutionAdapter(fill_mode="filled"),
        )
        requests = [
            request.model_copy(update={"reference_price": None})
            for request in execution_bundle.snapshot.order_requests
        ]
        snapshot = execution_bundle.snapshot.model_copy(update={"order_requests": requests})
        bundle = build_post_trade_bundle_from_execution_snapshot(snapshot)

        self.assertFalse(bundle.snapshot.quality.ok)
        self.assertTrue(
            all(item.arrival_price is None for item in bundle.snapshot.cost_estimates)
        )
        self.assertTrue(
            all(item.implementation_shortfall is None for item in bundle.snapshot.cost_estimates)
        )
        self.assertTrue(
            all(
                "tca_input_undisclosed: arrival price missing" in item.notes
                for item in bundle.snapshot.cost_estimates
            )
        )

    def test_staged_dry_run_is_not_counted_as_trade(self) -> None:
        risk_bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            risk_bundle.snapshot,
            context={
                "requested_mode": "dry_run",
                "operator_execute": False,
                "human_review_attested": True,
            },
        )
        bundle = build_post_trade_bundle_from_execution_snapshot(execution_bundle.snapshot)

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertEqual(bundle.snapshot.final_status, "staged_no_trade")
        self.assertIn(
            "staged_no_trade",
            {item.exception_type for item in bundle.snapshot.exceptions},
        )
        self.assertFalse(bundle.snapshot.portfolio_handoff)

    def test_missing_execution_receipt_fails_lineage(self) -> None:
        risk_bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            risk_bundle.snapshot,
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
            },
            adapter=FakePaperExecutionAdapter(fill_mode="filled"),
        )
        bad_snapshot = execution_bundle.snapshot.model_copy(update={"receipt_ref": ""})
        bundle = build_post_trade_bundle_from_execution_snapshot(bad_snapshot)

        self.assertFalse(bundle.snapshot.quality.ok)
        self.assertFalse(bundle.snapshot.quality.execution_receipt_present)
        self.assertEqual(bundle.snapshot.final_status, "lineage_failed")
        self.assertIn(
            "missing_execution_receipt",
            {item.exception_type for item in bundle.snapshot.exceptions},
        )

    def test_post_trade_graph_compiles(self) -> None:
        self.assertIsNotNone(post_trade_graph)

    def test_post_trade_graph_runs_with_execution_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(execution, "EXECUTION_NORMALIZED_ROOT", root / "execs"),
                patch.object(execution, "EXECUTION_RECEIPT_ROOT", root / "exec_receipts"),
                patch.object(post_trade, "POST_TRADE_NORMALIZED_ROOT", root / "pt"),
                patch.object(post_trade, "POST_TRADE_RECEIPT_ROOT", root / "pt_receipts"),
            ):
                risk_bundle = build_sample_risk_gate_bundle()
                execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
                    risk_bundle.snapshot,
                    context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
            },
                    adapter=FakePaperExecutionAdapter(fill_mode="filled"),
                )
                result = run_post_trade_graph(
                    execution_snapshot=execution_bundle.snapshot.model_dump(mode="json"),
                )

                final = result["final"]
                self.assertEqual(final["workflow"], "langgraph_post_trade_v1")
                self.assertEqual(final["final_status"], "reconciled_filled")
                self.assertTrue(final["quality_ok"])
                self.assertFalse(final["order_creation_allowed"])
                self.assertTrue(final["portfolio_handoff"])
                self.assertTrue(Path(final["payload_ref"]).exists())
                self.assertTrue(Path(final["receipt_ref"]).exists())


if __name__ == "__main__":
    unittest.main()
