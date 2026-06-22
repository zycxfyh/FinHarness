from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pydantic import ValidationError

from finharness.statecore.models import ReviewEvent
from finharness.statecore.proposals import (
    archived_proposal_ids,
    create_governed_proposal,
    create_governed_review_event,
    is_archived,
)
from finharness.statecore.store import StateCoreStoreError, init_state_core, write_records


class ReviewEventTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self._proposal("alloc_cash_buffer_low_2026-06-20")

    def _proposal(self, proposal_id: str) -> None:
        create_governed_proposal(
            kind="cash_buffer_low",
            claim="Cash covers 1.0 months",
            evidence={"runway": 1.0},
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id=proposal_id,
            idempotent=True,
        )

    def _event(self, kind: str, *, proposal_id: str = "alloc_cash_buffer_low_2026-06-20", **kw):
        return create_governed_review_event(
            proposal_id=proposal_id,
            kind=kind,  # type: ignore[arg-type]
            attester="operator",
            reason="reviewed during weekly check",
            engine=self.engine,
            receipt_root=self.receipt_root,
            **kw,
        )

    def _event_files(self) -> list[Path]:
        return sorted((self.receipt_root / "review-events").glob("*.json"))

    # --- receipt-backed + readable ----------------------------------------------------
    def test_annotation_writes_readable_receipt(self) -> None:
        write = self._event("annotation", text="watch the rate path")
        receipt = Path(write.receipt_ref)
        self.assertTrue(receipt.exists())
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "state_core_review_event")
        self.assertEqual(payload["review_event"]["kind"], "annotation")
        self.assertFalse(payload["governance"]["execution_allowed"])
        receipt.resolve().relative_to((self.receipt_root / "review-events").resolve())

    # --- content_hash is integrity, NOT idempotency -----------------------------------
    def test_repeated_annotation_is_a_new_event_not_a_noop(self) -> None:
        first = self._event("annotation", text="same note")
        second = self._event("annotation", text="same note")
        self.assertNotEqual(first.review_event.review_event_id, second.review_event.review_event_id)
        self.assertEqual(len(self._event_files()), 2)

    # --- archive derivation replays from append-only history ---------------------------
    def test_is_archived_derives_from_latest_toggle(self) -> None:
        self.assertFalse(is_archived("alloc_cash_buffer_low_2026-06-20", engine=self.engine))
        self._event("archive")
        self.assertTrue(is_archived("alloc_cash_buffer_low_2026-06-20", engine=self.engine))
        self._event("reopen")
        self.assertFalse(is_archived("alloc_cash_buffer_low_2026-06-20", engine=self.engine))
        self._event("archive")
        self.assertTrue(is_archived("alloc_cash_buffer_low_2026-06-20", engine=self.engine))

    def test_annotation_does_not_affect_archived_state(self) -> None:
        self._event("archive")
        self._event("annotation", text="note after archive")
        # Only archive/reopen toggle the derived state; annotation does not.
        self.assertTrue(is_archived("alloc_cash_buffer_low_2026-06-20", engine=self.engine))

    def test_archived_proposal_ids_reflects_latest_toggle(self) -> None:
        self._proposal("alloc_concentration_high_2026-06-20")
        self._event("archive")
        self._event("archive", proposal_id="alloc_concentration_high_2026-06-20")
        self._event("reopen", proposal_id="alloc_concentration_high_2026-06-20")
        self.assertEqual(
            archived_proposal_ids(self.engine), {"alloc_cash_buffer_low_2026-06-20"}
        )

    # --- DB failure leaves no residual receipt ----------------------------------------
    def test_db_write_failure_cleans_up_receipt(self) -> None:
        with mock.patch(
            "finharness.statecore.proposals.write_records",
            side_effect=StateCoreStoreError("disk full"),
        ), self.assertRaises(StateCoreStoreError):
            self._event("annotation", text="will fail")
        self.assertEqual(self._event_files(), [])  # receipt cleaned up on failure

    # --- validation -------------------------------------------------------------------
    def test_unknown_kind_is_rejected(self) -> None:
        with self.assertRaises((ValueError, ValidationError)):
            self._event("delete")

    def test_blank_attester_or_reason_is_rejected(self) -> None:
        with self.assertRaises((ValueError, ValidationError)):
            create_governed_review_event(
                proposal_id="alloc_cash_buffer_low_2026-06-20",
                kind="annotation",
                attester="  ",
                reason="x",
                engine=self.engine,
                receipt_root=self.receipt_root,
            )

    def test_unknown_proposal_raises(self) -> None:
        with self.assertRaises(KeyError):
            self._event("annotation", proposal_id="nope")

    def test_execution_allowed_cannot_be_persisted(self) -> None:
        # SQLModel table models skip field validators on construction; the DB
        # CheckConstraint is the real guard against persisting execution authority.
        bad = ReviewEvent(
            review_event_id="x",
            proposal_id="alloc_cash_buffer_low_2026-06-20",
            kind="annotation",
            attester="op",
            reason="r",
            execution_allowed=True,
        )
        with self.assertRaises(StateCoreStoreError):
            write_records([bad], engine=self.engine)


if __name__ == "__main__":
    unittest.main()
