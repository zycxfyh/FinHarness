"""Tests for governed ceiling resolution (G09)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.control_owner import certify_controls
from finharness.effective_ceilings import (
    CeilingResolutionError,
    enforce_request_limit,
    resolve_effective_ceiling,
)
from finharness.effective_rules import resolve_guard_thresholds
from finharness.lesson_loop import LessonDraft
from finharness.rule_change_ledger import RuleChange, promote_lesson_to_rule_change
from finharness.trading_guard import GuardThresholds


def _draft() -> LessonDraft:
    return LessonDraft(
        draft_id="lesson_draft_ceiling1",
        created_at_utc="2026-06-18T00:00:00+00:00",
        window_days=14,
        receipts_scanned=2,
        sources=["data/receipts/risk-gates"],
        status_counts={"ok": 2},
        quality_failure_count=0,
        top_blocking_reasons=[],
        observations=["operator explicitly reviewed ceiling"],
        proposed_rule_changes=[],
        receipt_refs=["receipt_a", "receipt_b"],
    )


def _baseline_evidence() -> dict[str, object]:
    return {
        "command": ["python", "-m", "unittest"],
        "test_modules": ["tests.test_execution"],
        "returncode": 0,
        "tests_run": 8,
        "failures": 0,
        "errors": 0,
    }


class EffectiveCeilingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.rule_state = self.root / "rule-changes"
        self.rule_receipts = self.root / "rule-receipts"
        self.cert_state = self.root / "certifications"
        self.cert_receipts = self.root / "cert-receipts"
        self.addCleanup(self.tmp.cleanup)

    def promote(self, *, target: str = "ceiling.max_live_notional", value=125.0):
        return promote_lesson_to_rule_change(
            lesson_draft=_draft(),
            rule_target=target,
            change_kind="threshold",
            old_value=50.0,
            new_value=value,
            rationale="human reviewed ceiling change with receipt lineage",
            attester="operator",
            lesson_doc_ref="docs/lessons/2026-06-18-ceiling.md",
            state_root=self.rule_state,
            receipt_root=self.rule_receipts,
        )

    def certify(self, authorized: dict[str, float]):
        return certify_controls(
            control_owner="Jane Control",
            review_cadence_days=30,
            baseline_passed=True,
            baseline_evidence=_baseline_evidence(),
            authorized_ceilings=authorized,
            state_root=self.cert_state,
            receipt_root=self.cert_receipts,
            created_at_utc="2026-06-18T00:00:00+00:00",
        )

    def test_empty_sources_yield_default_no_provenance(self) -> None:
        result = resolve_effective_ceiling(
            field="max_live_notional",
            default_ceiling=50.0,
            rule_change_root=self.rule_state,
            certification_root=self.cert_state,
        )

        self.assertEqual(result.effective_ceiling, 50.0)
        self.assertIsNone(result.provenance)
        self.assertEqual(result.ignored, [])

    def test_traceable_rule_change_can_raise_ceiling_with_provenance(self) -> None:
        change = self.promote(value=125.0)

        result = resolve_effective_ceiling(
            field="max_live_notional",
            default_ceiling=50.0,
            rule_change_root=self.rule_state,
            certification_root=self.cert_state,
        )

        self.assertEqual(result.effective_ceiling, 125.0)
        self.assertIsNotNone(result.provenance)
        self.assertEqual(result.provenance.source_type, "rule_change")
        self.assertEqual(result.provenance.source_id, change.rule_change_id)

    def test_untraceable_ceiling_change_is_ignored(self) -> None:
        rogue = RuleChange(
            rule_change_id="rulechg_rogue",
            created_at_utc="2026-06-18T00:00:00+00:00",
            rule_target="ceiling.max_live_notional",
            change_kind="threshold",
            old_value=50.0,
            new_value=500.0,
            rationale="no lesson lineage",
            attester="operator",
        )

        result = resolve_effective_ceiling(
            field="max_live_notional",
            default_ceiling=50.0,
            rule_changes=[rogue],
            owner_certs=[],
        )

        self.assertEqual(result.effective_ceiling, 50.0)
        self.assertIn("rulechg_rogue", result.ignored)

    def test_owner_certification_can_raise_ceiling_with_provenance(self) -> None:
        certification = self.certify({"ceiling.max_live_notional": 150.0})

        result = resolve_effective_ceiling(
            field="max_live_notional",
            default_ceiling=50.0,
            rule_change_root=self.rule_state,
            certification_root=self.cert_state,
        )

        self.assertEqual(result.effective_ceiling, 150.0)
        self.assertIsNotNone(result.provenance)
        self.assertEqual(result.provenance.source_type, "control_owner_certification")
        self.assertEqual(result.provenance.source_id, certification.certification_id)

    def test_guard_namespace_does_not_affect_ceiling_namespace(self) -> None:
        self.promote(target="guard.hard_stop_consecutive_losses", value=2)

        ceiling = resolve_effective_ceiling(
            field="max_live_notional",
            default_ceiling=50.0,
            rule_change_root=self.rule_state,
            certification_root=self.cert_state,
        )
        guard, provenance, ignored = resolve_guard_thresholds(ledger_root=self.rule_state)

        self.assertEqual(ceiling.effective_ceiling, 50.0)
        self.assertEqual(guard.hard_stop_consecutive_losses, 2)
        self.assertNotEqual(guard, GuardThresholds())
        self.assertTrue(provenance)
        self.assertEqual(ignored, [])

    def test_request_limit_is_clamped_to_effective_ceiling(self) -> None:
        enforced = enforce_request_limit(
            field="max_live_notional",
            default_ceiling=50.0,
            request_limit=10_000.0,
            rule_change_root=self.rule_state,
            certification_root=self.cert_state,
        )

        self.assertEqual(enforced.enforced_cap, 50.0)
        self.assertTrue(enforced.request_limit_clamped_to_ceiling)
        self.assertTrue(enforced.cap_invariant_holds)

    def test_bad_ceiling_source_fails_closed(self) -> None:
        self.rule_state.mkdir(parents=True)
        (self.rule_state / "rulechg_bad.json").write_text("{bad", encoding="utf-8")

        with self.assertRaises(CeilingResolutionError):
            resolve_effective_ceiling(
                field="max_live_notional",
                default_ceiling=50.0,
                rule_change_root=self.rule_state,
                certification_root=self.cert_state,
            )


if __name__ == "__main__":
    unittest.main()
