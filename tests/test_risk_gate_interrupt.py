"""Tests for the interactive human-review interrupt gate (Step 5).

Covers: fail-closed attestation default, interrupt pause on pending review,
resume with attestation upgrades decisions, resume without reason stays
fail-closed.
"""

from __future__ import annotations

import unittest
from uuid import uuid4

from finharness.proposal import build_proposal_bundle_from_validation_snapshot
from finharness.risk_gate import RiskGateContext, build_risk_gate_bundle_from_proposal_snapshot
from finharness.risk_gate_graph import (
    build_risk_gate_graph,
    resume_risk_gate_graph,
    run_risk_gate_graph_interactive,
)
from tests.test_proposal import build_sample_validation_bundle


def proposal_snapshot_payload() -> dict:
    validation_bundle = build_sample_validation_bundle()
    proposal_bundle = build_proposal_bundle_from_validation_snapshot(
        validation_bundle.snapshot
    )
    return proposal_bundle.snapshot.model_dump(mode="json")


class FailClosedDefaultTests(unittest.TestCase):
    def test_attestation_defaults_false(self) -> None:
        self.assertFalse(RiskGateContext().human_review_attested)

    def test_unattested_run_yields_needs_human_review(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(
            validation_bundle.snapshot
        )
        bundle = build_risk_gate_bundle_from_proposal_snapshot(proposal_bundle.snapshot)
        self.assertTrue(
            all(
                decision.decision == "needs_human_review"
                for decision in bundle.decisions
            )
        )
        self.assertFalse(bundle.snapshot.execution_handoff)


class InterruptGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = build_risk_gate_graph(interactive=True)
        self.payload = {
            "proposal_snapshot": proposal_snapshot_payload(),
            "risk_context": {},
            "symbols": [],
            "research_asset_context": {},
        }

    def test_run_pauses_at_human_gate_when_unattested(self) -> None:
        thread_id = f"test-{uuid4().hex[:8]}"
        result = run_risk_gate_graph_interactive(
            payload=self.payload, thread_id=thread_id, graph=self.graph
        )
        self.assertIn("__interrupt__", result)
        interrupt_payload = result["__interrupt__"][0].value
        self.assertIn("pending_decisions", interrupt_payload)
        self.assertTrue(interrupt_payload["pending_decisions"])

    def test_resume_with_attestation_approves(self) -> None:
        thread_id = f"test-{uuid4().hex[:8]}"
        paused = run_risk_gate_graph_interactive(
            payload=self.payload, thread_id=thread_id, graph=self.graph
        )
        self.assertIn("__interrupt__", paused)
        result = resume_risk_gate_graph(
            graph=self.graph,
            thread_id=thread_id,
            attest=True,
            reason="reviewed candidates in test",
        )
        self.assertNotIn("__interrupt__", result)
        final = result["final"]
        self.assertTrue(final["quality_ok"])
        self.assertTrue(final["execution_handoff"])
        event = result["human_review_event"]
        self.assertTrue(event["attested"])
        self.assertEqual(event["reason"], "reviewed candidates in test")
        decisions = result["decisions"]
        self.assertTrue(
            all(item["decision"] == "approved_for_paper_review" for item in decisions)
        )

    def test_resume_without_reason_stays_fail_closed(self) -> None:
        thread_id = f"test-{uuid4().hex[:8]}"
        run_risk_gate_graph_interactive(
            payload=self.payload, thread_id=thread_id, graph=self.graph
        )
        result = resume_risk_gate_graph(
            graph=self.graph, thread_id=thread_id, attest=True, reason="   "
        )
        decisions = result["decisions"]
        self.assertTrue(
            all(item["decision"] == "needs_human_review" for item in decisions)
        )
        self.assertNotIn("human_review_event", result)

    def test_resume_with_denial_stays_fail_closed(self) -> None:
        thread_id = f"test-{uuid4().hex[:8]}"
        run_risk_gate_graph_interactive(
            payload=self.payload, thread_id=thread_id, graph=self.graph
        )
        result = resume_risk_gate_graph(
            graph=self.graph, thread_id=thread_id, attest=False, reason="not convinced"
        )
        decisions = result["decisions"]
        self.assertTrue(
            all(item["decision"] == "needs_human_review" for item in decisions)
        )

    def test_attested_payload_does_not_pause(self) -> None:
        thread_id = f"test-{uuid4().hex[:8]}"
        payload = dict(self.payload)
        payload["risk_context"] = {"human_review_attested": True}
        result = run_risk_gate_graph_interactive(
            payload=payload, thread_id=thread_id, graph=self.graph
        )
        self.assertNotIn("__interrupt__", result)
        self.assertTrue(result["final"]["execution_handoff"])


if __name__ == "__main__":
    unittest.main()
