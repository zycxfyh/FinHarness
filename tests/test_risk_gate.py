from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.test_proposal import build_sample_validation_bundle

from finharness import events, hypotheses, interpretation, proposal, risk_gate, validation
from finharness.proposal import (
    ProposalCandidate,
    build_proposal_bundle_from_validation_snapshot,
)
from finharness.risk_gate import (
    RiskGateContext,
    build_risk_gate_bundle_from_proposal_snapshot,
    build_risk_gate_quality,
)
from finharness.risk_gate_graph import risk_gate_graph, run_risk_gate_graph


class RiskGateLayerTest(unittest.TestCase):
    def test_bundle_persists_risk_gate_snapshot_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "events_raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "events_normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "events_receipts"),
                patch.object(interpretation, "INTERPRETATION_NORMALIZED_ROOT", root / "ints"),
                patch.object(interpretation, "INTERPRETATION_RECEIPT_ROOT", root / "int_receipts"),
                patch.object(hypotheses, "HYPOTHESIS_NORMALIZED_ROOT", root / "hyps"),
                patch.object(hypotheses, "HYPOTHESIS_RECEIPT_ROOT", root / "hyp_receipts"),
                patch.object(validation, "VALIDATION_NORMALIZED_ROOT", root / "vals"),
                patch.object(validation, "VALIDATION_RECEIPT_ROOT", root / "val_receipts"),
                patch.object(proposal, "PROPOSAL_NORMALIZED_ROOT", root / "props"),
                patch.object(proposal, "PROPOSAL_RECEIPT_ROOT", root / "prop_receipts"),
                patch.object(risk_gate, "RISK_GATE_NORMALIZED_ROOT", root / "rgates"),
                patch.object(risk_gate, "RISK_GATE_RECEIPT_ROOT", root / "rgate_receipts"),
            ):
                validation_bundle = build_sample_validation_bundle()
                proposal_bundle = build_proposal_bundle_from_validation_snapshot(
                    validation_bundle.snapshot,
                )
                bundle = build_risk_gate_bundle_from_proposal_snapshot(
                    proposal_bundle.snapshot,
                    llm_enabled=True,
                    hermes_root="/root/projects/hermes-agent",
                )

                self.assertEqual(
                    bundle.snapshot.candidate_count,
                    proposal_bundle.snapshot.candidate_count,
                )
                self.assertEqual(
                    bundle.snapshot.decision_count,
                    proposal_bundle.snapshot.candidate_count,
                )
                self.assertTrue(bundle.snapshot.quality.ok)
                self.assertFalse(bundle.snapshot.execution_allowed)
                self.assertTrue(bundle.snapshot.execution_handoff)
                self.assertEqual(
                    bundle.snapshot.lineage.input_proposal_snapshot_id,
                    proposal_bundle.snapshot.proposal_snapshot_id,
                )
                self.assertEqual(bundle.snapshot.lineage.source.llm_provider, "hermes-agent")
                self.assertTrue(Path(bundle.snapshot.payload_ref).exists())
                self.assertTrue(Path(bundle.snapshot.receipt_ref).exists())
                for decision in bundle.snapshot.decisions:
                    self.assertEqual(decision.decision, "approved_for_paper_review")
                    self.assertTrue(decision.paper_review_allowed)
                    self.assertFalse(decision.live_execution_allowed)

    def test_live_request_is_hard_blocked_but_quality_passes(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        bundle = build_risk_gate_bundle_from_proposal_snapshot(
            proposal_bundle.snapshot,
            context={"requested_execution_mode": "live"},
        )

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertTrue(bundle.snapshot.quality.hard_blocks_enforced)
        self.assertFalse(bundle.snapshot.execution_allowed)
        self.assertTrue(all(decision.decision == "blocked" for decision in bundle.decisions))

    def test_missing_human_review_requests_human_review(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        bundle = build_risk_gate_bundle_from_proposal_snapshot(
            proposal_bundle.snapshot,
            context={"human_review_attested": False},
        )

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertTrue(
            all(decision.decision == "needs_human_review" for decision in bundle.decisions)
        )

    def test_quality_records_blocked_order_language(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        bad_candidate = ProposalCandidate.model_validate(
            proposal_bundle.snapshot.candidates[0].model_dump(mode="json")
            | {"rationale": "place order after risk gate"}
        )
        bad_snapshot = proposal_bundle.snapshot.model_copy(
            update={
                "candidates": [bad_candidate, *proposal_bundle.snapshot.candidates[1:]],
            }
        )
        bundle = build_risk_gate_bundle_from_proposal_snapshot(bad_snapshot)
        quality = build_risk_gate_quality(
            proposal_snapshot=bad_snapshot,
            context=RiskGateContext(),
            decisions=bundle.decisions,
        )

        self.assertFalse(quality.ok)
        self.assertFalse(quality.no_order_language)
        self.assertTrue(quality.blocked_language_hits)
        self.assertTrue(any(decision.decision == "blocked" for decision in bundle.decisions))

    def test_risk_gate_graph_compiles(self) -> None:
        self.assertIsNotNone(risk_gate_graph)

    def test_risk_gate_graph_runs_with_proposal_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "events_raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "events_normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "events_receipts"),
                patch.object(interpretation, "INTERPRETATION_NORMALIZED_ROOT", root / "ints"),
                patch.object(interpretation, "INTERPRETATION_RECEIPT_ROOT", root / "int_receipts"),
                patch.object(hypotheses, "HYPOTHESIS_NORMALIZED_ROOT", root / "hyps"),
                patch.object(hypotheses, "HYPOTHESIS_RECEIPT_ROOT", root / "hyp_receipts"),
                patch.object(validation, "VALIDATION_NORMALIZED_ROOT", root / "vals"),
                patch.object(validation, "VALIDATION_RECEIPT_ROOT", root / "val_receipts"),
                patch.object(proposal, "PROPOSAL_NORMALIZED_ROOT", root / "props"),
                patch.object(proposal, "PROPOSAL_RECEIPT_ROOT", root / "prop_receipts"),
                patch.object(risk_gate, "RISK_GATE_NORMALIZED_ROOT", root / "rgates"),
                patch.object(risk_gate, "RISK_GATE_RECEIPT_ROOT", root / "rgate_receipts"),
            ):
                validation_bundle = build_sample_validation_bundle()
                proposal_bundle = build_proposal_bundle_from_validation_snapshot(
                    validation_bundle.snapshot,
                )
                result = run_risk_gate_graph(
                    proposal_snapshot=proposal_bundle.snapshot.model_dump(mode="json"),
                    llm_enabled=True,
                    hermes_root="/root/projects/hermes-agent",
                )

                final = result["final"]
                self.assertEqual(final["workflow"], "langgraph_risk_gate_v1")
                self.assertEqual(final["decision_count"], proposal_bundle.snapshot.candidate_count)
                self.assertTrue(final["quality_ok"])
                self.assertFalse(final["execution_allowed"])
                self.assertTrue(final["execution_handoff"])
                self.assertEqual(final["consumer_handoff"]["consumer"], "execution_review")
                self.assertTrue(final["llm_enabled"])
                self.assertEqual(final["hermes_root"], "/root/projects/hermes-agent")


if __name__ == "__main__":
    unittest.main()
