"""Tests for B4: lesson -> rule-change lineage."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.lesson_loop import LessonDraft
from finharness.rule_change_ledger import (
    RuleChange,
    RuleChangePromotionError,
    audit_untraceable,
    is_traceable,
    load_rule_changes,
    promote_lesson_to_rule_change,
    trace_rule_change,
)


def _draft(receipt_refs=None) -> LessonDraft:
    return LessonDraft(
        draft_id="lesson_draft_test123",
        created_at_utc="2026-06-13T00:00:00+00:00",
        window_days=14,
        receipts_scanned=3,
        sources=["data/receipts/risk-gates"],
        status_counts={"ok": 3},
        quality_failure_count=0,
        top_blocking_reasons=[("Human review attestation is required", 2)],
        observations=["attestation blocks recur"],
        proposed_rule_changes=[],
        receipt_refs=receipt_refs if receipt_refs is not None else ["r1", "r2", "r3"],
    )


class RuleChangeLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "rule-changes"
        self.receipts = Path(self.tmp.name) / "receipts"
        self.addCleanup(self.tmp.cleanup)

    def _promote(self, **overrides):
        kwargs = {
            "lesson_draft": _draft(),
            "rule_target": "guard.hard_stop_consecutive_losses",
            "change_kind": "threshold",
            "old_value": 3,
            "new_value": 2,
            "rationale": "attestation blocks recur; tighten the loss streak stop",
            "attester": "operator",
            "lesson_doc_ref": "docs/lessons/2026-06-13-attestation.md",
            "state_root": self.state,
            "receipt_root": self.receipts,
        }
        kwargs.update(overrides)
        return promote_lesson_to_rule_change(**kwargs)

    # --- authorization-before-action -------------------------------------

    def test_promote_without_attester_is_refused(self) -> None:
        with self.assertRaises(RuleChangePromotionError):
            self._promote(attester="")

    def test_promote_without_rationale_is_refused(self) -> None:
        with self.assertRaises(RuleChangePromotionError):
            self._promote(rationale="   ")

    def test_promote_from_lesson_without_receipts_is_refused(self) -> None:
        with self.assertRaises(RuleChangePromotionError):
            self._promote(lesson_draft=_draft(receipt_refs=[]))

    # --- lineage ----------------------------------------------------------

    def test_promoted_change_carries_lineage(self) -> None:
        change = self._promote()
        self.assertEqual(change.lesson_draft_id, "lesson_draft_test123")
        self.assertEqual(change.receipt_refs, ["r1", "r2", "r3"])
        self.assertTrue(is_traceable(change))

    def test_trace_returns_full_chain(self) -> None:
        change = self._promote()
        traced = trace_rule_change(change.rule_change_id, state_root=self.state)
        self.assertEqual(traced["lesson"]["lesson_draft_id"], "lesson_draft_test123")
        self.assertEqual(traced["receipts"], ["r1", "r2", "r3"])
        self.assertTrue(traced["traceable"])

    def test_hand_built_change_without_lineage_is_not_traceable(self) -> None:
        rogue = RuleChange(
            rule_change_id="rulechg_rogue",
            created_at_utc="2026-06-13T00:00:00+00:00",
            rule_target="guard.hard_stop_drawdown_pct",
            change_kind="threshold",
            new_value=-10.0,
            rationale="because I feel like it",
            attester="operator",
        )
        self.assertFalse(is_traceable(rogue))

    # --- persistence + audit ---------------------------------------------

    def test_ledger_round_trips(self) -> None:
        change = self._promote()
        loaded = load_rule_changes(self.state)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].rule_change_id, change.rule_change_id)

    def test_audit_untraceable_is_empty_for_promoted_changes(self) -> None:
        self._promote()
        self.assertEqual(audit_untraceable(self.state), [])

    def test_receipt_is_written_with_lineage(self) -> None:
        change = self._promote()
        receipts = list(self.receipts.glob("*.json"))
        self.assertEqual(len(receipts), 1)
        import json

        payload = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "rule_change_promotion")
        self.assertEqual(payload["lineage"]["receipt_count"], 3)
        self.assertEqual(payload["rule_change"]["rule_change_id"], change.rule_change_id)


if __name__ == "__main__":
    unittest.main()
