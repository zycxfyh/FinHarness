from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_proposal import build_sample_validation_bundle

from finharness import (
    events,
    execution,
    hypotheses,
    interpretation,
    proposal,
    risk_gate,
    validation,
)
from finharness.execution import (
    ExecutionContext,
    FakePaperExecutionAdapter,
    build_execution_bundle_from_risk_gate_snapshot,
    build_execution_intents,
    build_order_requests,
)
from finharness.execution_graph import execution_graph, run_execution_graph
from finharness.proposal import build_proposal_bundle_from_validation_snapshot
from finharness.risk_gate import build_risk_gate_bundle_from_proposal_snapshot


def build_sample_risk_gate_bundle(
    *,
    risk_context: dict[str, object] | None = None,
) -> risk_gate.RiskGateBundle:
    validation_bundle = build_sample_validation_bundle()
    proposal_bundle = build_proposal_bundle_from_validation_snapshot(
        validation_bundle.snapshot,
    )
    return build_risk_gate_bundle_from_proposal_snapshot(
        proposal_bundle.snapshot,
        context=risk_context,
    )


class ExecutionLayerTest(unittest.TestCase):
    def test_dry_run_stages_order_without_submission(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            bundle.snapshot,
            context={"requested_mode": "dry_run", "operator_execute": False},
        )

        self.assertTrue(execution_bundle.snapshot.quality.ok)
        self.assertEqual(execution_bundle.snapshot.final_status, "staged")
        self.assertEqual(execution_bundle.snapshot.intent_count, bundle.snapshot.decision_count)
        self.assertEqual(
            execution_bundle.snapshot.order_request_count,
            bundle.snapshot.decision_count,
        )
        self.assertTrue(
            all(event.event_type == "staged" for event in execution_bundle.snapshot.events)
        )
        self.assertFalse(execution_bundle.snapshot.execution_allowed)

    def test_paper_execute_submits_to_fake_adapter(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            bundle.snapshot,
            context={"requested_mode": "paper", "operator_execute": True},
            adapter=FakePaperExecutionAdapter(fill_mode="filled"),
        )

        self.assertTrue(execution_bundle.snapshot.quality.ok)
        self.assertEqual(execution_bundle.snapshot.final_status, "filled")
        statuses = [event.status for event in execution_bundle.snapshot.events]
        self.assertIn("submitted_paper", statuses)
        self.assertIn("filled", statuses)
        self.assertTrue(execution_bundle.snapshot.post_trade_handoff)
        self.assertFalse(execution_bundle.snapshot.execution_allowed)

    def test_live_mode_is_blocked_before_submit(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            bundle.snapshot,
            context={"requested_mode": "live", "operator_execute": True},
        )

        self.assertFalse(execution_bundle.snapshot.quality.ok)
        self.assertFalse(execution_bundle.snapshot.quality.paper_mode_required)
        self.assertFalse(execution_bundle.snapshot.quality.live_mode_blocked)
        self.assertEqual(execution_bundle.snapshot.final_status, "blocked_before_submit")
        self.assertEqual(execution_bundle.snapshot.order_request_count, 0)

    def test_blocked_risk_gate_does_not_create_order_request(self) -> None:
        bundle = build_sample_risk_gate_bundle(risk_context={"requested_execution_mode": "live"})
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            bundle.snapshot,
            context={"requested_mode": "paper", "operator_execute": True},
        )

        self.assertTrue(execution_bundle.snapshot.quality.ok)
        self.assertEqual(execution_bundle.snapshot.intent_count, 0)
        self.assertEqual(execution_bundle.snapshot.order_request_count, 0)
        self.assertEqual(execution_bundle.snapshot.final_status, "blocked_before_submit")

    def test_idempotency_key_is_deterministic_and_adapter_rejects_duplicate(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        context = ExecutionContext(requested_mode="paper", operator_execute=True)
        intents = build_execution_intents(
            risk_gate_snapshot=bundle.snapshot,
            context=context,
        )
        first_requests = build_order_requests(
            risk_gate_snapshot=bundle.snapshot,
            context=context,
            source=execution.ExecutionSourceSpec(adapter_mode="paper"),
            intents=intents,
        )
        second_requests = build_order_requests(
            risk_gate_snapshot=bundle.snapshot,
            context=context,
            source=execution.ExecutionSourceSpec(adapter_mode="paper"),
            intents=intents,
        )
        self.assertEqual(
            [request.idempotency_key for request in first_requests],
            [request.idempotency_key for request in second_requests],
        )

        adapter = FakePaperExecutionAdapter(fill_mode="accepted")
        adapter.submit(first_requests[0])
        duplicate_events = adapter.submit(first_requests[0])
        self.assertEqual(duplicate_events[-1].status, "rejected")
        self.assertEqual(duplicate_events[-1].raw_status, "duplicate_client_order_id")

    def test_partial_fill_and_cancel_events_are_preserved(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            bundle.snapshot,
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "requested_quantity": 4,
                "cancel_after_submit": True,
            },
            adapter=FakePaperExecutionAdapter(fill_mode="partial"),
        )

        statuses = [event.status for event in execution_bundle.snapshot.events]
        self.assertIn("partially_filled", statuses)
        self.assertIn("cancel_requested", statuses)
        self.assertIn("canceled", statuses)
        self.assertTrue(
            all(
                event.raw_status and isinstance(event.raw_event, dict)
                for event in execution_bundle.snapshot.events
            )
        )

    def test_execution_graph_compiles(self) -> None:
        self.assertIsNotNone(execution_graph)

    def test_execution_graph_runs_with_risk_gate_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "events_raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "events_normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "events_receipts"),
                patch.object(interpretation, "INTERPRETATION_NORMALIZED_ROOT", root / "ints"),
                patch.object(
                    interpretation,
                    "INTERPRETATION_RECEIPT_ROOT",
                    root / "int_receipts",
                ),
                patch.object(hypotheses, "HYPOTHESIS_NORMALIZED_ROOT", root / "hyps"),
                patch.object(hypotheses, "HYPOTHESIS_RECEIPT_ROOT", root / "hyp_receipts"),
                patch.object(validation, "VALIDATION_NORMALIZED_ROOT", root / "vals"),
                patch.object(validation, "VALIDATION_RECEIPT_ROOT", root / "val_receipts"),
                patch.object(proposal, "PROPOSAL_NORMALIZED_ROOT", root / "props"),
                patch.object(proposal, "PROPOSAL_RECEIPT_ROOT", root / "prop_receipts"),
                patch.object(risk_gate, "RISK_GATE_NORMALIZED_ROOT", root / "rgates"),
                patch.object(risk_gate, "RISK_GATE_RECEIPT_ROOT", root / "rgate_receipts"),
                patch.object(execution, "EXECUTION_NORMALIZED_ROOT", root / "execs"),
                patch.object(execution, "EXECUTION_RECEIPT_ROOT", root / "exec_receipts"),
            ):
                risk_bundle = build_sample_risk_gate_bundle()
                result = run_execution_graph(
                    risk_gate_snapshot=risk_bundle.snapshot.model_dump(mode="json"),
                    execution_context={"requested_mode": "paper", "operator_execute": True},
                    fake_fill_mode="filled",
                )

                final = result["final"]
                self.assertEqual(final["workflow"], "langgraph_execution_v1")
                self.assertEqual(final["mode"], "paper")
                self.assertEqual(final["intent_count"], risk_bundle.snapshot.decision_count)
                self.assertEqual(
                    final["order_request_count"],
                    risk_bundle.snapshot.decision_count,
                )
                self.assertEqual(final["final_status"], "filled")
                self.assertTrue(final["quality_ok"])
                self.assertFalse(final["execution_allowed"])
                self.assertTrue(Path(final["payload_ref"]).exists())
                self.assertTrue(Path(final["receipt_ref"]).exists())


if __name__ == "__main__":
    unittest.main()
