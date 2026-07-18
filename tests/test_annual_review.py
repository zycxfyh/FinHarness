from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from finharness.annual_review import compute_annual_review, record_annual_review
from finharness.statecore.models import ReceiptIndex
from finharness.statecore.proposal_version import (
    ProposalVersionExpectation,
    resolve_current_proposal_version,
)
from finharness.statecore.proposals import (
    create_governed_attestation,
    create_governed_proposal,
)
from finharness.statecore.store import init_state_core, read_all
from tests._scaffold import VALID_SCAFFOLD


class AnnualReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _proposal(
        self,
        proposal_id: str,
        kind: str,
        created_at_utc: str,
        *,
        claim: str = "claim",
        evidence: dict[str, object] | None = None,
    ):
        return create_governed_proposal(
            kind=kind,
            claim=claim,
            evidence=evidence or {},
            source_refs=[],
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id=proposal_id,
            created_at_utc=created_at_utc,
            idempotent=True,
        )

    def test_decision_panel_over_rolling_window(self) -> None:
        self._proposal("a", "cash_buffer_low", "2026-03-01T00:00:00+00:00")
        self._proposal("b", "concentration_high", "2026-05-01T00:00:00+00:00")
        self._proposal("c", "tax_window", "2024-01-01T00:00:00+00:00")  # outside window
        ver = resolve_current_proposal_version(
            "a", engine=self.engine, receipt_root=self.receipt_root
        )
        expectation = ProposalVersionExpectation(
            proposal_id="a",
            proposal_version_id=ver.proposal_version_id,
            receipt_ref=ver.receipt_ref,
        )
        create_governed_attestation(
            proposal_id="a",
            decision="approved",
            attester="xzh",
            reason="reviewed the evidence",
            expectation=expectation,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

        review = compute_annual_review(
            self.engine, as_of_date=date(2026, 6, 20), lesson_scan_root=self.root
        )

        self.assertEqual(review.period_label, "12 months to 2026-06-20")
        self.assertEqual(review.candidate_count, 2)
        self.assertEqual(
            review.candidates_by_kind, {"cash_buffer_low": 1, "concentration_high": 1}
        )
        self.assertEqual(review.open_count, 1)
        self.assertEqual(review.attested_count, 1)
        self.assertEqual(review.approved_count, 1)
        self.assertEqual(review.rejected_count, 0)
        self.assertFalse(review.execution_allowed)

    def test_calendar_year_period_selects_year(self) -> None:
        self._proposal("a", "cash_buffer_low", "2026-03-01T00:00:00+00:00")
        self._proposal("c", "tax_window", "2024-07-01T00:00:00+00:00")

        review_2026 = compute_annual_review(self.engine, year=2026, lesson_scan_root=self.root)
        self.assertEqual(review_2026.period_label, "2026")
        self.assertEqual(review_2026.period_start, "2026-01-01")
        self.assertEqual(review_2026.period_end, "2026-12-31")
        self.assertEqual(review_2026.candidate_count, 1)

        review_2024 = compute_annual_review(self.engine, year=2024, lesson_scan_root=self.root)
        self.assertEqual(review_2024.candidate_count, 1)

    def test_b4_lesson_closure_via_rule_change_ledger(self) -> None:
        lessons = self.root / "lessons"
        lessons.mkdir()
        rules = self.root / "rules"
        rules.mkdir()
        (lessons / "L1.json").write_text(
            json.dumps({"draft_id": "L1", "created_at_utc": "2026-03-01T00:00:00+00:00"}),
            encoding="utf-8",
        )
        (lessons / "L2.json").write_text(
            json.dumps({"draft_id": "L2", "created_at_utc": "2026-03-02T00:00:00+00:00"}),
            encoding="utf-8",
        )
        (rules / "rulechg_1.json").write_text(
            json.dumps(
                {
                    "rule_change_id": "rulechg_1",
                    "created_at_utc": "2026-03-05T00:00:00+00:00",
                    "rule_target": "guard.cash_runway_target_months",
                    "change_kind": "threshold",
                    "rationale": "raise emergency-fund target after a near-miss",
                    "attester": "xzh",
                    "lesson_draft_id": "L1",
                    "lesson_doc_ref": "docs/lessons/2026-L1.md",
                    "receipt_refs": ["data/receipts/lessons/L1.json"],
                    "status": "active",
                }
            ),
            encoding="utf-8",
        )

        review = compute_annual_review(
            self.engine,
            as_of_date=date(2026, 6, 20),
            lesson_receipt_root=lessons,
            lesson_scan_root=self.root,
            rule_change_state_root=rules,
        )

        self.assertEqual(review.lessons_total, 2)
        self.assertEqual(review.lessons_closed, 1)
        self.assertEqual(review.lessons_open, ("L2",))
        self.assertEqual(review.untraceable_rule_changes, ())

    def test_future_rule_change_does_not_close_period_lesson(self) -> None:
        lessons = self.root / "lessons"
        lessons.mkdir()
        rules = self.root / "rules"
        rules.mkdir()
        (lessons / "L1.json").write_text(
            json.dumps({"draft_id": "L1", "created_at_utc": "2026-03-01T00:00:00+00:00"}),
            encoding="utf-8",
        )
        (rules / "rulechg_future.json").write_text(
            json.dumps(
                {
                    "rule_change_id": "rulechg_future",
                    "created_at_utc": "2027-01-01T00:00:00+00:00",
                    "rule_target": "guard.cash_runway_target_months",
                    "change_kind": "threshold",
                    "rationale": "future promotion must not rewrite this period",
                    "attester": "xzh",
                    "lesson_draft_id": "L1",
                    "lesson_doc_ref": "docs/lessons/2026-L1.md",
                    "receipt_refs": ["data/receipts/lessons/L1.json"],
                    "status": "active",
                }
            ),
            encoding="utf-8",
        )
        (rules / "rulechg_future_untraceable.json").write_text(
            json.dumps(
                {
                    "rule_change_id": "rulechg_future_untraceable",
                    "created_at_utc": "2027-01-01T00:00:00+00:00",
                    "rule_target": "guard.cash_runway_target_months",
                    "change_kind": "threshold",
                    "rationale": "future untraceable change must not pollute 2026",
                    "attester": "xzh",
                    "lesson_draft_id": "L1",
                    "lesson_doc_ref": None,
                    "receipt_refs": [],
                    "status": "active",
                }
            ),
            encoding="utf-8",
        )

        review = compute_annual_review(
            self.engine,
            as_of_date=date(2026, 6, 20),
            lesson_receipt_root=lessons,
            lesson_scan_root=self.root,
            rule_change_state_root=rules,
        )

        self.assertEqual(review.lessons_total, 1)
        self.assertEqual(review.lessons_closed, 0)
        self.assertEqual(review.lessons_open, ("L1",))
        self.assertEqual(review.untraceable_rule_changes, ())

    def test_corrupt_lesson_receipt_becomes_data_gap_not_crash(self) -> None:
        lessons = self.root / "lessons"
        lessons.mkdir()
        (lessons / "bad.json").write_text("{ not valid json", encoding="utf-8")

        review = compute_annual_review(
            self.engine,
            as_of_date=date(2026, 6, 20),
            lesson_receipt_root=lessons,
            lesson_scan_root=self.root,
        )

        self.assertEqual(review.lessons_total, 0)
        self.assertTrue(any("lesson receipt unreadable" in gap for gap in review.data_gaps))

    def test_proposal_revision_chain_failures_become_data_gaps(self) -> None:
        missing = self._proposal(
            "missing-rev",
            "cash_buffer_low",
            "2026-03-01T00:00:00+00:00",
        )
        Path(missing.receipt_ref).unlink()

        corrupt = self._proposal(
            "corrupt-rev",
            "cash_buffer_low",
            "2026-03-01T00:00:00+00:00",
        )
        Path(corrupt.receipt_ref).write_text("{ not valid json", encoding="utf-8")

        self._proposal(
            "cycle-rev",
            "cash_buffer_low",
            "2026-03-01T00:00:00+00:00",
            claim="v1",
            evidence={"x": 1},
        )
        latest = self._proposal(
            "cycle-rev",
            "cash_buffer_low",
            "2026-03-02T00:00:00+00:00",
            claim="v2",
            evidence={"x": 2},
        )
        latest_path = Path(latest.receipt_ref)
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
        payload["supersedes"] = latest.receipt_ref
        latest_path.write_text(json.dumps(payload), encoding="utf-8")

        review = compute_annual_review(
            self.engine, as_of_date=date(2026, 6, 20), lesson_scan_root=self.root
        )

        self.assertEqual(review.candidate_count, 3)
        self.assertTrue(
            any("missing-rev" in gap and "missing" in gap for gap in review.data_gaps)
        )
        self.assertTrue(
            any("corrupt-rev" in gap and "unreadable" in gap for gap in review.data_gaps)
        )
        self.assertTrue(
            any("cycle-rev" in gap and "cycle" in gap for gap in review.data_gaps)
        )

    def test_lesson_loop_signals_are_part_of_report(self) -> None:
        source = self.root / "data" / "receipts" / "validations"
        source.mkdir(parents=True)
        (source / "receipt_quality.json").write_text(
            json.dumps(
                {
                    "kind": "validation",
                    "created_at_utc": "2026-03-01T00:00:00+00:00",
                    "status": "done",
                    "quality": {"ok": False},
                    "snapshot": {
                        "final_status": "lineage_failed",
                        "decisions": [
                            {"blocking_reasons": ["missing source receipt"]},
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )

        review = compute_annual_review(
            self.engine,
            as_of_date=date(2026, 6, 20),
            lesson_scan_root=self.root,
            lesson_scan_sources=("data/receipts/validations",),
        )

        self.assertEqual(review.lesson_receipts_scanned, 1)
        self.assertTrue(
            any("failed quality gates" in item for item in review.lesson_observations)
        )
        self.assertTrue(
            any("lineage.required" in item for item in review.proposed_rule_changes)
        )

    def test_evolution_count_and_record_writes_receipt(self) -> None:
        # Two content revisions of the same proposal -> it counts as "evolved".
        self._proposal(
            "ev",
            "cash_buffer_low",
            "2026-03-01T00:00:00+00:00",
            claim="v1",
            evidence={"x": 1},
        )
        self._proposal(
            "ev",
            "cash_buffer_low",
            "2026-03-02T00:00:00+00:00",
            claim="v2",
            evidence={"x": 2},
        )

        review, receipt_ref = record_annual_review(
            self.engine,
            receipt_root=self.root / "annual",
            as_of_date=date(2026, 6, 20),
            lesson_scan_root=self.root,
        )

        self.assertGreaterEqual(review.candidates_with_revisions, 1)
        self.assertFalse(review.execution_allowed)
        self.assertTrue(Path(receipt_ref).exists())
        receipts = [
            r for r in read_all(ReceiptIndex, engine=self.engine) if r.kind == "annual_review"
        ]
        self.assertEqual(len(receipts), 1)


if __name__ == "__main__":
    unittest.main()
