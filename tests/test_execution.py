from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    NAUTILUS_ORDER_BACKEND,
    NAUTILUS_PAPER_ADAPTER_NAME,
    ExecutionContext,
    FakePaperExecutionAdapter,
    NautilusPaperExecutionAdapter,
    build_execution_bundle_from_risk_gate_snapshot,
    build_execution_intents,
    build_order_requests,
)
from finharness.execution_graph import execution_graph, run_execution_graph
from finharness.market_access_ledger import MarketAccessLedgerError
from finharness.proposal import build_proposal_bundle_from_validation_snapshot
from finharness.risk_gate import build_risk_gate_bundle_from_proposal_snapshot
from tests.test_proposal import build_sample_validation_bundle


def build_sample_risk_gate_bundle(
    *,
    risk_context: dict[str, object] | None = None,
) -> risk_gate.RiskGateBundle:
    validation_bundle = build_sample_validation_bundle()
    proposal_bundle = build_proposal_bundle_from_validation_snapshot(
        validation_bundle.snapshot,
    )
    # Attestation is fail-closed; fixtures must declare it like a human would.
    context: dict[str, object] = {"human_review_attested": True}
    context.update(risk_context or {})
    return build_risk_gate_bundle_from_proposal_snapshot(
        proposal_bundle.snapshot,
        context=context,
    )


class ExecutionLayerTest(unittest.TestCase):
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

    def test_dry_run_stages_order_without_submission(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            bundle.snapshot,
            context={
                "requested_mode": "dry_run",
                "operator_execute": False,
                "human_review_attested": True,
            },
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
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
            },
            adapter=FakePaperExecutionAdapter(fill_mode="filled"),
        )

        self.assertTrue(execution_bundle.snapshot.quality.ok)
        self.assertEqual(execution_bundle.snapshot.final_status, "filled")
        statuses = [event.status for event in execution_bundle.snapshot.events]
        self.assertIn("submitted_paper", statuses)
        self.assertIn("filled", statuses)
        self.assertTrue(execution_bundle.snapshot.post_trade_handoff)
        self.assertFalse(execution_bundle.snapshot.execution_allowed)

    def test_paper_execute_blocks_when_aggregate_limit_exceeded(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            bundle.snapshot,
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
                "requested_quantity": 2,
                "reference_price": 100.0,
                "market_access_limit": {
                    "max_window_notional": 150.0,
                    "max_window_order_count": 10,
                },
            },
            adapter=FakePaperExecutionAdapter(fill_mode="filled"),
        )

        self.assertEqual(execution_bundle.snapshot.final_status, "blocked_before_submit")
        self.assertTrue(
            any(
                "market-access ledger blocked order request" in event.raw_event.get("reason", "")
                for event in execution_bundle.snapshot.events
            )
        )
        self.assertFalse(execution_bundle.snapshot.execution_allowed)

    def test_paper_execute_does_not_submit_when_market_access_record_fails(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        adapter = FakePaperExecutionAdapter(fill_mode="filled")

        with patch(
            "finharness.execution.record_consumption",
            side_effect=MarketAccessLedgerError("disk full"),
        ):
            execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
                bundle.snapshot,
                context={
                    "requested_mode": "paper",
                    "operator_execute": True,
                    "human_review_attested": True,
                },
                adapter=adapter,
            )

        self.assertEqual(execution_bundle.snapshot.final_status, "blocked_before_submit")
        self.assertEqual(adapter.submitted_keys, set())
        self.assertTrue(
            any(
                "market-access ledger consumption failed before paper submit"
                in event.raw_event.get("reason", "")
                for event in execution_bundle.snapshot.events
            )
        )
        self.assertFalse(execution_bundle.snapshot.execution_allowed)

    def test_default_paper_execute_uses_nautilus_typed_order_adapter(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            bundle.snapshot,
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
                "order_type": "limit",
                "reference_price": 123.45,
            },
        )

        self.assertEqual(execution_bundle.source.adapter_name, NAUTILUS_PAPER_ADAPTER_NAME)
        self.assertEqual(execution_bundle.snapshot.final_status, "accepted")
        self.assertFalse(execution_bundle.snapshot.execution_allowed)
        raw_events = [event.raw_event for event in execution_bundle.snapshot.events]
        nautilus_orders = [
            item["order"]
            for item in raw_events
            if item.get("backend") == NAUTILUS_ORDER_BACKEND and "order" in item
        ]
        self.assertTrue(nautilus_orders)
        self.assertEqual(nautilus_orders[0]["type"], "LIMIT")
        self.assertEqual(nautilus_orders[0]["price"], "123.45000000")
        self.assertEqual(nautilus_orders[0]["status"], "INITIALIZED")

    def test_nautilus_adapter_rejects_no_live_authority_by_type(self) -> None:
        self.assertEqual(NautilusPaperExecutionAdapter.adapter_mode, "paper")

    def test_live_mode_is_blocked_before_submit(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        execution_bundle = build_execution_bundle_from_risk_gate_snapshot(
            bundle.snapshot,
            context={
                "requested_mode": "live",
                "operator_execute": True,
                "human_review_attested": True,
            },
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
            context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
            },
        )

        self.assertTrue(execution_bundle.snapshot.quality.ok)
        self.assertEqual(execution_bundle.snapshot.intent_count, 0)
        self.assertEqual(execution_bundle.snapshot.order_request_count, 0)
        self.assertEqual(execution_bundle.snapshot.final_status, "blocked_before_submit")

    def test_idempotency_key_is_deterministic_and_adapter_rejects_duplicate(self) -> None:
        bundle = build_sample_risk_gate_bundle()
        context = ExecutionContext(
            requested_mode="paper", operator_execute=True, human_review_attested=True
        )
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
                "human_review_attested": True,
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
                    execution_context={
                        "requested_mode": "paper",
                        "operator_execute": True,
                        "human_review_attested": True,
                    },
                )

                final = result["final"]
                self.assertEqual(final["workflow"], "langgraph_execution_v1")
                self.assertEqual(final["mode"], "paper")
                self.assertEqual(final["intent_count"], risk_bundle.snapshot.decision_count)
                self.assertEqual(
                    final["order_request_count"],
                    risk_bundle.snapshot.decision_count,
                )
                self.assertEqual(final["final_status"], "accepted")
                self.assertTrue(final["quality_ok"])
                self.assertFalse(final["execution_allowed"])
                execution_events = result["snapshot"]["events"]
                self.assertTrue(
                    any(
                        event["raw_event"].get("backend") == NAUTILUS_ORDER_BACKEND
                        for event in execution_events
                    )
                )
                self.assertTrue(
                    all(
                        event["raw_event"].get("fill_mode") is None
                        for event in execution_events
                    )
                )
                self.assertEqual(
                    result["snapshot"]["lineage"]["adapter_name"],
                    NAUTILUS_PAPER_ADAPTER_NAME,
                )
                self.assertTrue(Path(final["payload_ref"]).exists())
                self.assertTrue(Path(final["receipt_ref"]).exists())

    def test_execution_graph_uses_fake_only_when_explicitly_requested(self) -> None:
        risk_bundle = build_sample_risk_gate_bundle()
        result = run_execution_graph(
            risk_gate_snapshot=risk_bundle.snapshot.model_dump(mode="json"),
            execution_context={
                "requested_mode": "paper",
                "operator_execute": True,
                "human_review_attested": True,
            },
            execution_adapter="fake",
            fake_fill_mode="filled",
        )

        self.assertEqual(result["final"]["final_status"], "filled")
        self.assertEqual(result["snapshot"]["lineage"]["adapter_name"], "fake_paper_adapter")
        self.assertTrue(
            any(
                event["raw_event"].get("fill_mode") == "filled"
                for event in result["snapshot"]["events"]
            )
        )
        self.assertFalse(result["final"]["execution_allowed"])

    def test_execution_graph_live_mode_is_blocked_before_submit(self) -> None:
        risk_bundle = build_sample_risk_gate_bundle()
        result = run_execution_graph(
            risk_gate_snapshot=risk_bundle.snapshot.model_dump(mode="json"),
            execution_context={
                "requested_mode": "live",
                "operator_execute": True,
                "human_review_attested": True,
            },
        )

        self.assertEqual(result["final"]["final_status"], "blocked_before_submit")
        self.assertEqual(result["final"]["order_request_count"], 0)
        self.assertFalse(result["final"]["quality_ok"])
        self.assertFalse(result["final"]["execution_allowed"])
        self.assertTrue(
            any(
                event["raw_event"].get("reason")
                == "live execution is blocked in Layer 9 MVP"
                for event in result["snapshot"]["events"]
            )
        )


if __name__ == "__main__":
    unittest.main()
