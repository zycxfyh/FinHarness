from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.statecore.models import Proposal, ReceiptIndex
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core, read_all


class GovernedProposalReceiptRevisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _write(self, *, claim: str, evidence: dict[str, object]):
        return create_governed_proposal(
            kind="cash_buffer_low",
            claim=claim,
            evidence=evidence,
            source_refs=["data/receipts/snap.json"],
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id="alloc_cash_buffer_low_2026-06-20",
            idempotent=True,
        )

    def _proposal_receipts(self) -> list[ReceiptIndex]:
        return [
            receipt
            for receipt in read_all(ReceiptIndex, engine=self.engine)
            if receipt.kind == "state_core_proposal"
        ]

    def _receipt_files(self) -> list[Path]:
        return sorted((self.receipt_root / "proposals").glob("*.json"))

    def test_unchanged_content_does_not_append_revision(self) -> None:
        first = self._write(claim="Cash covers 1.0 months", evidence={"runway": 1.0})
        again = self._write(claim="Cash covers 1.0 months", evidence={"runway": 1.0})

        # Idempotent + unchanged content: same latest receipt, no new revision.
        self.assertEqual(again.receipt_ref, first.receipt_ref)
        self.assertEqual(len(read_all(Proposal, engine=self.engine)), 1)
        self.assertEqual(len(self._proposal_receipts()), 1)
        self.assertEqual(len(self._receipt_files()), 1)

    def test_changed_content_appends_revision_and_links_chain(self) -> None:
        first = self._write(claim="Cash covers 1.0 months", evidence={"runway": 1.0})
        second = self._write(claim="Cash covers 0.5 months", evidence={"runway": 0.5})

        # New revision: distinct receipt, single current-state proposal, history kept.
        self.assertNotEqual(second.receipt_ref, first.receipt_ref)
        self.assertEqual(len(read_all(Proposal, engine=self.engine)), 1)
        self.assertEqual(len(self._proposal_receipts()), 2)
        self.assertEqual(len(self._receipt_files()), 2)

        # Proposal points at the latest; the chain links back via supersedes.
        proposal = read_all(Proposal, engine=self.engine)[0]
        self.assertEqual(proposal.receipt_ref, second.receipt_ref)

        latest = json.loads(Path(second.receipt_ref).read_text(encoding="utf-8"))
        prior = json.loads(Path(first.receipt_ref).read_text(encoding="utf-8"))
        self.assertEqual(latest["supersedes"], first.receipt_ref)
        self.assertIsNone(prior["supersedes"])
        self.assertNotEqual(latest["content_hash"], prior["content_hash"])

    def test_reverting_to_prior_content_still_appends_revision(self) -> None:
        first = self._write(claim="Cash covers 1.0 months", evidence={"runway": 1.0})
        second = self._write(claim="Cash covers 0.5 months", evidence={"runway": 0.5})
        third = self._write(claim="Cash covers 1.0 months", evidence={"runway": 1.0})

        # Returning to prior content is still a new point in the review timeline.
        self.assertNotEqual(third.receipt_ref, first.receipt_ref)
        self.assertEqual(len(read_all(Proposal, engine=self.engine)), 1)
        self.assertEqual(len(self._proposal_receipts()), 3)
        self.assertEqual(len(self._receipt_files()), 3)

        first_payload = json.loads(Path(first.receipt_ref).read_text(encoding="utf-8"))
        second_payload = json.loads(Path(second.receipt_ref).read_text(encoding="utf-8"))
        third_payload = json.loads(Path(third.receipt_ref).read_text(encoding="utf-8"))

        self.assertIsNone(first_payload["supersedes"])
        self.assertEqual(second_payload["supersedes"], first.receipt_ref)
        self.assertEqual(third_payload["supersedes"], second.receipt_ref)
        self.assertEqual(third_payload["content_hash"], first_payload["content_hash"])


if __name__ == "__main__":
    unittest.main()
