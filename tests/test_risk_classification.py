"""P5 v0 ① — high-risk classification and the approval-time counter-evidence gate.

Covers the product value of P5's first brick: a high-risk governed proposal may be
recorded and reviewed, but it cannot be *approved* without stating counter-evidence.
The gate lives at human approval (attestation), never at proposal creation, so the
auto-creators are never forced to fabricate counter-evidence.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.api.app import create_app
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.models import Attestation, Proposal
from finharness.statecore.proposals import (
    create_governed_attestation,
    create_governed_proposal,
)
from finharness.statecore.risk_classification import (
    HIGH_RISK_KINDS,
    HighRiskConfirmationError,
    is_high_risk,
)
from finharness.statecore.store import init_state_core, read_all
from tests._scaffold import VALID_SCAFFOLD
from tests.asgi_test_client import AsgiTestClient

SCAFFOLD_WITH_COUNTER = {
    **VALID_SCAFFOLD,
    "counter_evidence": "A reversal back under the threshold would prove the thesis wrong.",
}


class RiskClassifierTest(unittest.TestCase):
    def test_high_risk_kinds_classify_true(self) -> None:
        for kind in HIGH_RISK_KINDS:
            self.assertTrue(is_high_risk(kind, {}), kind)

    def test_ordinary_kind_classifies_false(self) -> None:
        self.assertFalse(is_high_risk("cash_buffer_low", {}))
        self.assertFalse(is_high_risk("rebalance_review", None))

    def test_evidence_leverage_signal(self) -> None:
        self.assertTrue(is_high_risk("rebalance_review", {"leverage": 2.0}))
        # leverage of 1 (or below) is not leveraged.
        self.assertFalse(is_high_risk("rebalance_review", {"leverage": 1}))
        # a bool must not be read as a leverage ratio.
        self.assertFalse(is_high_risk("rebalance_review", {"leverage": True}))

    def test_evidence_margin_and_liquidation_signals(self) -> None:
        self.assertTrue(is_high_risk("rebalance_review", {"margin_used": 1500.0}))
        self.assertTrue(is_high_risk("rebalance_review", {"liquidation_risk": True}))
        self.assertFalse(is_high_risk("rebalance_review", {"margin_used": 0}))


class HighRiskApprovalGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _proposal(self, proposal_id: str, scaffold: dict[str, object]) -> None:
        create_governed_proposal(
            kind="concentration_high",
            claim="Top holding is over the concentration threshold.",
            evidence={},
            decision_scaffold=scaffold,
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id=proposal_id,
        )

    def _attest(self, proposal_id: str, decision: str) -> None:
        create_governed_attestation(
            proposal_id=proposal_id,
            decision=decision,  # type: ignore[arg-type]
            attester="xzh",
            reason="reviewed the evidence",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

    def test_high_risk_without_counter_evidence_can_be_created(self) -> None:
        # Creation is never gated on counter-evidence — only approval is.
        self._proposal("p_create", VALID_SCAFFOLD)
        rows = read_all(Proposal, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertNotIn("counter_evidence", rows[0].decision_scaffold)

    def test_high_risk_approval_without_counter_evidence_is_fail_closed(self) -> None:
        self._proposal("p_gate", VALID_SCAFFOLD)
        with self.assertRaises(HighRiskConfirmationError):
            self._attest("p_gate", "approved")
        # Fail-closed before any write: no attestation row, no attestation receipt.
        self.assertEqual(read_all(Attestation, engine=self.engine), [])
        self.assertFalse((self.receipt_root / "attestations").exists())

    def test_high_risk_rejection_is_not_gated(self) -> None:
        self._proposal("p_reject", VALID_SCAFFOLD)
        self._attest("p_reject", "rejected")  # must not raise
        rows = read_all(Attestation, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].decision, "rejected")

    def test_high_risk_approval_with_counter_evidence_succeeds(self) -> None:
        self._proposal("p_ok", SCAFFOLD_WITH_COUNTER)
        self._attest("p_ok", "approved")  # must not raise
        rows = read_all(Attestation, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].decision, "approved")

    def test_ordinary_approval_without_counter_evidence_succeeds(self) -> None:
        create_governed_proposal(
            kind="cash_buffer_low",
            claim="Cash runway is low.",
            evidence={"runway": 1.0},
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id="p_ordinary",
        )
        self._attest("p_ordinary", "approved")  # must not raise
        self.assertEqual(len(read_all(Attestation, engine=self.engine)), 1)


class HighRiskApprovalApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.app = create_app(
            state_core_engine=self.engine, receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _create(self, scaffold: dict[str, object]) -> str:
        resp = self.client.post(
            "/proposals",
            json={
                "kind": "concentration_high",
                "claim": "Top holding is over the concentration threshold.",
                "decision_scaffold": scaffold,
            },
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()["proposal"]["proposal_id"]

    def test_high_risk_proposal_creates_and_is_open_for_review(self) -> None:
        proposal_id = self._create(VALID_SCAFFOLD)
        open_list = self.client.get("/proposals", params={"status": "open"})
        self.assertEqual(open_list.status_code, 200)
        ids = [item["proposal"]["proposal_id"] for item in open_list.json()]
        self.assertIn(proposal_id, ids)

    def test_approve_high_risk_without_counter_evidence_is_422_and_writes_nothing(self) -> None:
        proposal_id = self._create(VALID_SCAFFOLD)
        resp = self.client.post(
            f"/proposals/{proposal_id}/attest",
            json={"decision": "approved", "reason": "looks fine"},
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(read_all(Attestation, engine=self.engine), [])

    def test_approve_high_risk_with_counter_evidence_succeeds(self) -> None:
        proposal_id = self._create(SCAFFOLD_WITH_COUNTER)
        resp = self.client.post(
            f"/proposals/{proposal_id}/attest",
            json={"decision": "approved", "reason": "reviewed counter-evidence"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["attestation"]["decision"], "approved")


if __name__ == "__main__":
    unittest.main()
