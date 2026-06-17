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
            all(item.inputs_disclosed for item in bundle.snapshot.cost_estimates)
        )
        self.assertTrue(bundle.snapshot.portfolio_handoff)
        self.assertFalse(bundle.snapshot.order_creation_allowed)

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
        self.assertIn(
            "execution_rejected",
            {item.exception_type for item in bundle.snapshot.exceptions},
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
