from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session, select

from finharness.api.app import create_app
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.diff import diff_snapshots
from finharness.statecore.models import (
    Account,
    Attestation,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
)
from finharness.statecore.store import init_state_core, open_state_core, write_records
from tests._scaffold import VALID_SCAFFOLD
from tests.asgi_test_client import AsgiTestClient


class StateCoreVerticalReconstructionTest(unittest.TestCase):
    """Capstone: reconstruct a full proposal decision from DB + receipts alone.

    This is the executable form of the brief's definition-of-done #1: with only
    the state-core DB and the receipt files on disk (no chat logs, no retained
    API response), recover what state was seen, what changed, what the proposal
    claimed, why a human approved, and that execution stayed blocked end to end.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "state-core.sqlite"
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.db_path)
        self._seed_two_snapshots()
        self.client = AsgiTestClient(
            create_app(
                state_core_engine=self.engine,
                receipt_root=str(self.receipt_root),
                local_operator_context=LocalOperatorContext("test_harness"),
            )
        )
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _seed_two_snapshots(self) -> None:
        account = Account(
            account_id="acct_cap",
            kind="broker",
            venue="alpaca-paper",
            display_name="Capstone Account",
            source_refs=["data/receipts/before.json"],
        )
        before = Snapshot(
            snapshot_id="snap_before",
            kind="portfolio",
            as_of_utc="2026-06-17T09:00:00+00:00",
            payload={"source": "test_fixture"},
            source_refs=["data/receipts/before.json"],
        )
        after = Snapshot(
            snapshot_id="snap_after",
            kind="portfolio",
            as_of_utc="2026-06-17T10:00:00+00:00",
            payload={"source": "test_fixture"},
            source_refs=["data/receipts/after.json"],
        )
        positions = [
            Position(
                position_id="pos_b_spy",
                snapshot_id="snap_before",
                account_id="acct_cap",
                symbol="SPY",
                quantity=1.0,
                market_value=100.0,
                valuation_currency="USD",
                unit_price=100.0,
                price_currency="USD",
                valued_at_utc="2026-06-17T09:00:00+00:00",
                price_source_ref="data/receipts/before.json",
                valuation_status="valued",
                source_refs=["data/receipts/before.json"],
            ),
            Position(
                position_id="pos_a_spy",
                snapshot_id="snap_after",
                account_id="acct_cap",
                symbol="SPY",
                quantity=2.0,
                market_value=210.0,
                valuation_currency="USD",
                unit_price=105.0,
                price_currency="USD",
                valued_at_utc="2026-06-17T10:00:00+00:00",
                price_source_ref="data/receipts/after.json",
                valuation_status="valued",
                source_refs=["data/receipts/after.json"],
            ),
        ]
        write_records([account, before, after, *positions], engine=self.engine)

    def test_proposal_decision_reconstructable_from_db_and_receipts_only(self) -> None:
        # 1) what changed: read-only diff over the state that was seen
        diff = self.client.get(
            "/diff",
            params={
                "before_snapshot_id": "snap_before",
                "after_snapshot_id": "snap_after",
            },
        ).json()
        self.assertFalse(diff["execution_allowed"])
        mv_delta = diff["total_market_value_delta"]
        self.assertEqual(mv_delta, 110.0)

        # 2) AI proposes governed advice that references the seen state
        create = self.client.post(
            "/proposals",
            json={
                "kind": "risk_alert",
                "claim": "SPY exposure roughly doubled since the prior snapshot.",
                "evidence": {
                    "before_snapshot_id": "snap_before",
                    "after_snapshot_id": "snap_after",
                    "total_market_value_delta": mv_delta,
                },
                "source_refs": ["data/receipts/before.json", "data/receipts/after.json"],
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        self.assertEqual(create.status_code, 200)
        proposal_id = create.json()["proposal"]["proposal_id"]
        version = self.client.get(
            f"/proposals/{proposal_id}/revisions"
        ).json()["revisions"][0]

        # 3) a human attests; approval is review only, never execution
        attest = self.client.post(
            f"/proposals/{proposal_id}/attest",
            json={
                "decision": "approved",
                "reason": "Reviewed; will trim SPY at the next session.",
                "expected_proposal_version_id": version["receipt_id"],
                "expected_proposal_receipt_ref": version["receipt_ref"],
            },
        )
        self.assertEqual(attest.status_code, 200)
        self.assertFalse(attest.json()["execution_allowed"])

        # --- RECONSTRUCTION: reopen the DB and read receipt files from disk.
        # Nothing from the responses above is reused except proposal_id, exactly
        # as a human reopening the case later would have. ---
        fresh = open_state_core(self.db_path)
        try:
            with Session(fresh) as session:
                proposal = session.get(Proposal, proposal_id)
                self.assertIsNotNone(proposal)
                attestations = list(
                    session.exec(
                        select(Attestation).where(Attestation.proposal_id == proposal_id)
                    ).all()
                )
                attestation_index = list(
                    session.exec(
                        select(ReceiptIndex).where(
                            ReceiptIndex.kind == "state_core_attestation"
                        )
                    ).all()
                )
                # the state that was seen is still queryable and the change recomputes
                recomputed = diff_snapshots(
                    proposal.evidence["before_snapshot_id"],
                    proposal.evidence["after_snapshot_id"],
                    engine=fresh,
                )

            # the AI's claim, with execution structurally blocked
            self.assertEqual(proposal.kind, "risk_alert")
            self.assertFalse(proposal.execution_allowed)
            self.assertIn("Not execution authorization.", proposal.non_claims)
            self.assertEqual(
                recomputed.total_market_value_delta,
                proposal.evidence["total_market_value_delta"],
            )

            # the proposal receipt file, located via the DB column
            proposal_receipt = json.loads(
                Path(proposal.receipt_ref).read_text(encoding="utf-8")
            )
            self.assertEqual(proposal_receipt["kind"], "state_core_proposal")
            self.assertEqual(proposal_receipt["proposal"]["claim"], proposal.claim)
            self.assertFalse(proposal_receipt["governance"]["execution_allowed"])
            self.assertTrue(proposal_receipt["governance"]["not_execution_authorization"])

            # the human decision and its written reason
            self.assertEqual(len(attestations), 1)
            attestation = attestations[0]
            self.assertEqual(attestation.decision, "approved")
            self.assertEqual(attestation.attester, "legacy-local:test_harness")
            self.assertTrue(attestation.reason.strip())

            # the attestation receipt file, located via the receipt index
            self.assertEqual(len(attestation_index), 1)
            attestation_receipt = json.loads(
                Path(attestation_index[0].path).read_text(encoding="utf-8")
            )
            self.assertEqual(attestation_receipt["kind"], "state_core_attestation")
            self.assertEqual(attestation_receipt["proposal_id"], proposal_id)
            self.assertFalse(attestation_receipt["governance"]["execution_allowed"])
            self.assertTrue(
                attestation_receipt["governance"]["approved_is_not_execution_authorization"]
            )
        finally:
            fresh.dispose()


if __name__ == "__main__":
    unittest.main()
