from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session

from finharness.statecore.models import Proposal
from finharness.statecore.proposal_version import (
    ProposalVersionResolutionError,
    require_current_proposal_version,
    resolve_current_proposal_version,
)
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD


class ProposalVersionResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _write(self, claim: str):
        return create_governed_proposal(
            proposal_id="proposal_version_test",
            kind="allocation_review",
            claim=claim,
            evidence={"source": "fixture"},
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=self.receipt_root,
            idempotent=True,
        )

    def test_current_version_has_explicit_supersession_lineage(self) -> None:
        first = self._write("version one")
        second = self._write("version two")

        current = resolve_current_proposal_version(
            "proposal_version_test",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

        self.assertEqual(current.receipt_ref, second.receipt_ref)
        self.assertNotEqual(current.proposal_version_id, current.content_hash)
        self.assertEqual(len(current.lineage), 2)
        self.assertEqual(
            current.lineage[0].supersedes_version_id,
            current.lineage[1].proposal_version_id,
        )
        self.assertEqual(current.lineage[1].receipt_ref, first.receipt_ref)

    def test_revert_repeats_hash_but_mints_new_version_identity(self) -> None:
        self._write("original")
        original = resolve_current_proposal_version(
            "proposal_version_test", engine=self.engine, receipt_root=self.receipt_root
        )
        self._write("changed")
        self._write("original")
        reverted = resolve_current_proposal_version(
            "proposal_version_test", engine=self.engine, receipt_root=self.receipt_root
        )

        self.assertEqual(original.content_hash, reverted.content_hash)
        self.assertNotEqual(original.proposal_version_id, reverted.proposal_version_id)
        self.assertEqual(len(reverted.lineage), 3)

    def test_stale_version_and_receipt_are_rejected_for_write_admission(self) -> None:
        first = self._write("one")
        first_version = resolve_current_proposal_version(
            "proposal_version_test", engine=self.engine, receipt_root=self.receipt_root
        )
        self._write("two")

        with self.assertRaisesRegex(ProposalVersionResolutionError, "not current") as raised:
            require_current_proposal_version(
                "proposal_version_test",
                expected_version_id=first_version.proposal_version_id,
                expected_receipt_ref=first.receipt_ref,
                engine=self.engine,
                receipt_root=self.receipt_root,
            )
        self.assertEqual(raised.exception.code, "proposal_version_conflict")

    def test_row_receipt_divergence_blocks_resolution(self) -> None:
        self._write("receipt truth")
        with Session(self.engine) as session:
            row = session.get(Proposal, "proposal_version_test")
            assert row is not None
            row.claim = "forged row"
            session.add(row)
            session.commit()

        with self.assertRaises(ProposalVersionResolutionError) as raised:
            resolve_current_proposal_version(
                "proposal_version_test", engine=self.engine, receipt_root=self.receipt_root
            )
        self.assertEqual(raised.exception.code, "row_receipt_divergence")

    def test_missing_and_corrupt_receipts_fail_closed(self) -> None:
        write = self._write("valid")
        Path(write.receipt_ref).unlink()
        with self.assertRaises(ProposalVersionResolutionError) as missing:
            resolve_current_proposal_version(
                "proposal_version_test", engine=self.engine, receipt_root=self.receipt_root
            )
        self.assertEqual(missing.exception.code, "receipt_chain_invalid")

        write = self._write("new after missing")
        Path(write.receipt_ref).write_text("{broken", encoding="utf-8")
        with self.assertRaises(ProposalVersionResolutionError) as corrupt:
            resolve_current_proposal_version(
                "proposal_version_test", engine=self.engine, receipt_root=self.receipt_root
            )
        self.assertEqual(corrupt.exception.code, "receipt_chain_invalid")

    def test_payload_hash_tampering_blocks_resolution(self) -> None:
        write = self._write("valid")
        path = Path(write.receipt_ref)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["content_hash"] = "0" * 64
        path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(ProposalVersionResolutionError) as raised:
            resolve_current_proposal_version(
                "proposal_version_test", engine=self.engine, receipt_root=self.receipt_root
            )
        self.assertEqual(raised.exception.code, "receipt_content_hash_invalid")


if __name__ == "__main__":
    unittest.main()
