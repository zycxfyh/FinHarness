from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session

from finharness.agent_tools import draft_agent_review_note_from_context_payload
from finharness.review_read import (
    read_compare_marks,
    read_proposal_timeline,
    read_retrospective,
    read_review_queue,
)
from finharness.statecore.models import Proposal
from tests._review_fixtures import ReviewFixture


class ReviewReadTimelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = ReviewFixture()
        self.addCleanup(self.fx.cleanup)
        self.fx.proposal("p1")

    def test_missing_proposal_returns_none(self) -> None:
        self.assertIsNone(read_proposal_timeline(self.fx.engine, "nope"))

    def test_merges_attestation_and_review_event_newest_first(self) -> None:
        self.fx.attest("p1")
        self.fx.event("p1", "annotation", text="watch the rate path")
        timeline = read_proposal_timeline(self.fx.engine, "p1")
        assert timeline is not None
        self.assertFalse(timeline.is_archived)
        self.assertEqual(
            {entry.source_type for entry in timeline.entries},
            {"attestation", "review_event"},
        )
        stamps = [entry.created_at_utc for entry in timeline.entries]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_archive_then_reopen_derives_is_archived(self) -> None:
        self.fx.event("p1", "archive")
        self.assertTrue(read_proposal_timeline(self.fx.engine, "p1").is_archived)
        self.fx.event("p1", "reopen")
        self.assertFalse(read_proposal_timeline(self.fx.engine, "p1").is_archived)


class ReviewReadCompareMarksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = ReviewFixture()
        self.addCleanup(self.fx.cleanup)
        self.fx.proposal("A")
        self.fx.proposal("B")

    def test_empty_when_no_compare_marks(self) -> None:
        self.assertEqual(read_compare_marks(self.fx.engine), [])

    def test_reverse_and_repeat_collapse_to_one_pair_latest_wins(self) -> None:
        self.fx.event("A", "compare_mark", compare_with="B")  # A->B
        self.fx.event("B", "compare_mark", compare_with="A")  # B->A (same unordered pair)
        last = self.fx.event("A", "compare_mark", compare_with="B")  # repeat A->B, newest

        pairs = read_compare_marks(self.fx.engine)
        self.assertEqual(len(pairs), 1)  # canonical {A,B}, deduped
        self.assertEqual(pairs[0].review_event_id, last.review_event.review_event_id)
        self.assertEqual((pairs[0].proposal_id, pairs[0].compare_with), ("A", "B"))
        self.assertIsNone(pairs[0].missing_side)
        self.assertTrue(pairs[0].proposal_exists and pairs[0].compare_with_exists)

    def test_missing_side_flagged_not_crashed(self) -> None:
        self.fx.event("A", "compare_mark", compare_with="B")
        with Session(self.fx.engine) as session:
            session.delete(session.get(Proposal, "B"))
            session.commit()
        pairs = read_compare_marks(self.fx.engine)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].missing_side, "right")
        self.assertFalse(pairs[0].compare_with_exists)
        self.assertTrue(pairs[0].data_gaps)


class ReviewReadQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = ReviewFixture()
        self.addCleanup(self.fx.cleanup)

    def test_active_queue_excludes_closed_by_default_and_can_include_them(self) -> None:
        self.fx.proposal("open", source_refs=["context://open"])
        self.fx.proposal("attested", source_refs=["context://attested"])
        self.fx.attest("attested")
        self.fx.proposal("archived", source_refs=["context://archived"])
        self.fx.event("archived", "archive")

        active = read_review_queue(self.fx.engine, receipt_root=self.fx.receipt_root)
        self.assertEqual([item.proposal_id for item in active.items], ["open"])
        self.assertEqual(active.items[0].status, "needs_human_review")
        self.assertEqual(active.items[0].evidence_status, "complete")
        self.assertFalse(active.items[0].execution_allowed)
        self.assertFalse(active.items[0].authority_transition)

        all_items = read_review_queue(
            self.fx.engine,
            receipt_root=self.fx.receipt_root,
            include_closed=True,
        )
        statuses = {item.proposal_id: item.status for item in all_items.items}
        self.assertEqual(statuses["attested"], "reviewed")
        self.assertEqual(statuses["archived"], "archived")

    def test_agent_review_note_enters_review_queue_triage(self) -> None:
        self.fx.proposal("note_target", source_refs=["context://proposal"])
        draft_agent_review_note_from_context_payload(
            proposal_id="note_target",
            review_kind="risk_check",
            suggested_severity="high",
            summary="Liquidity evidence needs a second look.",
            rationale="The proposal does not show near-term cash timing.",
            findings=["Drift evidence exists."],
            risks=["Cash timing could change the review outcome."],
            open_questions=["Is the latest cashflow context current?"],
            evidence_refs=["evidence://drift"],
            source_refs=["context://proposal_timeline"],
            context_pack_refs=["context_pack://proposal_timeline"],
            data_gaps=["No cashflow context pack cited."],
            engine=self.fx.engine,
            receipt_root=self.fx.receipt_root,
        )

        queue = read_review_queue(self.fx.engine, receipt_root=self.fx.receipt_root)
        item = queue.items[0]

        self.assertEqual(item.proposal_id, "note_target")
        self.assertEqual(item.priority, "high")
        self.assertEqual(item.review_note_count, 1)
        self.assertEqual(
            item.latest_review_note_summary,
            "Liquidity evidence needs a second look.",
        )
        self.assertEqual(item.open_questions, ["Is the latest cashflow context current?"])
        self.assertEqual(item.risks, ["Cash timing could change the review outcome."])
        self.assertEqual(item.data_gaps, ["No cashflow context pack cited."])
        self.assertIn("answer Agent open questions", item.next_actions)
        self.assertFalse(item.execution_allowed)

    def test_duplicate_candidate_is_triage_hint_not_state_change(self) -> None:
        self.fx.proposal(
            "dup_a",
            kind="rebalance_review",
            claim="Review the same target allocation.",
            source_refs=["context://dup"],
        )
        self.fx.proposal(
            "dup_b",
            kind="rebalance_review",
            claim="Review the same target allocation.",
            source_refs=["context://dup"],
        )

        queue = read_review_queue(self.fx.engine, receipt_root=self.fx.receipt_root)
        by_id = {item.proposal_id: item for item in queue.items}

        self.assertEqual(by_id["dup_a"].duplicate_candidates, ["dup_b"])
        self.assertEqual(by_id["dup_b"].duplicate_candidates, ["dup_a"])
        self.assertIn(
            "compare duplicate candidates before progressing review",
            by_id["dup_a"].next_actions,
        )
        self.assertFalse(by_id["dup_a"].execution_allowed)


class ReviewReadRetrospectiveTest(unittest.TestCase):
    def test_empty_roots_return_none_and_no_rule_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            model = read_retrospective(Path(tmp) / "annual-review", Path(tmp) / "rules")
        self.assertIsNone(model.retrospective)
        self.assertIsNone(model.retrospective_receipt_ref)
        self.assertEqual(model.rule_changes, [])

    def test_latest_receipt_fields_pass_through(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            annual = Path(tmp) / "annual-review"
            annual.mkdir(parents=True)
            (annual / "r.json").write_text(
                json.dumps(
                    {
                        "kind": "annual_review",
                        "created_at_utc": "2026-06-01T00:00:00+00:00",
                        "lessons_closed": 2,
                        "lessons_open": ["L1"],
                    }
                ),
                encoding="utf-8",
            )
            model = read_retrospective(annual, Path(tmp) / "rules")
        assert model.retrospective is not None
        self.assertEqual(model.retrospective["lessons_closed"], 2)
        self.assertEqual(model.retrospective["lessons_open"], ["L1"])
        self.assertIn("r.json", model.retrospective_receipt_ref or "")


if __name__ == "__main__":
    unittest.main()
