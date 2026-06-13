"""Tests for B4 enforcement: effective guard thresholds resolved from the ledger."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.effective_rules import resolve_guard_thresholds
from finharness.lesson_loop import LessonDraft
from finharness.rule_change_ledger import promote_lesson_to_rule_change
from finharness.trading_guard import GuardThresholds


def _draft() -> LessonDraft:
    return LessonDraft(
        draft_id="lesson_draft_eff1",
        created_at_utc="2026-06-13T00:00:00+00:00",
        window_days=14,
        receipts_scanned=3,
        sources=["data/receipts/post-trade"],
        status_counts={"ok": 3},
        quality_failure_count=0,
        top_blocking_reasons=[],
        observations=["loss streak hard-stop hit repeatedly"],
        proposed_rule_changes=[],
        receipt_refs=["r1", "r2", "r3"],
    )


class EffectiveRulesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "rule-changes"
        self.receipts = Path(self.tmp.name) / "receipts"
        self.addCleanup(self.tmp.cleanup)

    def _promote(self, *, rule_target: str, new_value, change_kind="threshold"):
        return promote_lesson_to_rule_change(
            lesson_draft=_draft(),
            rule_target=rule_target,
            change_kind=change_kind,
            old_value=3,
            new_value=new_value,
            rationale="loss streak hard-stop recurs; tighten",
            attester="operator",
            lesson_doc_ref="docs/lessons/2026-06-13-loss-streak.md",
            state_root=self.ledger,
            receipt_root=self.receipts,
        )

    def test_empty_ledger_yields_defaults_no_provenance(self) -> None:
        effective, provenance, ignored = resolve_guard_thresholds(ledger_root=self.ledger)
        self.assertEqual(effective, GuardThresholds())
        self.assertEqual(provenance, {})
        self.assertEqual(ignored, [])

    def test_promoted_threshold_change_binds_with_provenance(self) -> None:
        change = self._promote(
            rule_target="guard.hard_stop_consecutive_losses", new_value=2
        )
        effective, provenance, ignored = resolve_guard_thresholds(ledger_root=self.ledger)
        # The promoted value now binds; the field traces to the rule change.
        self.assertEqual(effective.hard_stop_consecutive_losses, 2)
        self.assertEqual(provenance["hard_stop_consecutive_losses"], change.rule_change_id)
        self.assertEqual(ignored, [])
        # Untouched fields keep their defaults.
        self.assertEqual(effective.hard_stop_drawdown_pct, GuardThresholds().hard_stop_drawdown_pct)

    def test_int_field_is_coerced(self) -> None:
        self._promote(rule_target="guard.hard_stop_consecutive_losses", new_value="2")
        effective, _, _ = resolve_guard_thresholds(ledger_root=self.ledger)
        self.assertIsInstance(effective.hard_stop_consecutive_losses, int)
        self.assertEqual(effective.hard_stop_consecutive_losses, 2)

    def test_unknown_field_is_ignored_not_applied(self) -> None:
        change = self._promote(rule_target="guard.does_not_exist", new_value=1)
        effective, provenance, ignored = resolve_guard_thresholds(ledger_root=self.ledger)
        self.assertEqual(effective, GuardThresholds())
        self.assertEqual(provenance, {})
        self.assertIn(change.rule_change_id, ignored)

    def test_non_guard_target_is_skipped(self) -> None:
        self._promote(rule_target="risk.max_paper_notional", new_value=500)
        effective, provenance, ignored = resolve_guard_thresholds(ledger_root=self.ledger)
        self.assertEqual(effective, GuardThresholds())
        self.assertEqual(provenance, {})
        self.assertEqual(ignored, [])


if __name__ == "__main__":
    unittest.main()
