"""Tests for the Loop 4 v0 lesson drafting pass."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from finharness.lesson_loop import (
    draft_lessons,
    persist_lesson_draft,
    render_markdown,
    scan_receipts,
)


def write_receipt(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class LessonLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        now = datetime.now(UTC).isoformat()
        old = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        write_receipt(
            self.root / "data/receipts/risk-gates/r1.json",
            {
                "kind": "risk_gate_processing",
                "created_at_utc": now,
                "status": "ok",
                "snapshot": {
                    "quality": {"ok": True},
                    "decisions": [
                        {"blocking_reasons": ["Human review attestation is required."]}
                    ],
                },
            },
        )
        write_receipt(
            self.root / "data/receipts/executions/e1.json",
            {
                "kind": "execution_processing",
                "created_at_utc": now,
                "status": "failed",
                "snapshot": {
                    "quality": {"ok": False},
                    "final_status": "blocked_before_submit",
                    "events": [
                        {
                            "event_type": "blocked",
                            "raw_event": {"reason": "no approved decisions"},
                        }
                    ],
                },
            },
        )
        write_receipt(
            self.root / "data/receipts/executions/old.json",
            {
                "kind": "execution_processing",
                "created_at_utc": old,
                "status": "ok",
                "snapshot": {"quality": {"ok": True}},
            },
        )

    def test_scan_respects_window(self) -> None:
        digests = scan_receipts(root=self.root, window_days=14)
        self.assertEqual(len(digests), 2)
        digests_long = scan_receipts(root=self.root, window_days=365)
        self.assertEqual(len(digests_long), 3)

    def test_draft_aggregates_failures_and_blocking_reasons(self) -> None:
        draft = draft_lessons(root=self.root, window_days=14, use_llm=False)
        self.assertEqual(draft.receipts_scanned, 2)
        self.assertEqual(draft.quality_failure_count, 1)
        reasons = [reason for reason, _ in draft.top_blocking_reasons]
        self.assertIn("no approved decisions", reasons)
        self.assertIsNone(draft.llm_narrative)
        self.assertEqual(draft.promotion_state, "draft")

    def test_empty_window_still_produces_honest_draft(self) -> None:
        draft = draft_lessons(
            root=self.root / "nowhere", window_days=14, use_llm=False
        )
        self.assertEqual(draft.receipts_scanned, 0)
        self.assertTrue(any("no evidence" in item.lower() for item in draft.observations))

    def test_persist_writes_markdown_and_receipt(self) -> None:
        draft = draft_lessons(root=self.root, window_days=14, use_llm=False)
        refs = persist_lesson_draft(
            draft,
            doc_root=self.root / "docs/lessons/drafts",
            receipt_root=self.root / "data/receipts/lessons",
        )
        self.assertTrue(refs["doc_ref"].endswith(".md"))
        files = list((self.root / "docs/lessons/drafts").glob("*.md"))
        self.assertEqual(len(files), 1)
        content = files[0].read_text(encoding="utf-8")
        self.assertIn("DRAFT", content)
        self.assertIn("human", content)
        self.assertTrue(
            (self.root / "data/receipts/lessons" / f"{draft.draft_id}.json").exists()
        )

    def test_markdown_never_claims_authority(self) -> None:
        draft = draft_lessons(root=self.root, window_days=14, use_llm=False)
        text = render_markdown(draft)
        self.assertIn("not a lesson until a human promotes it", text)


if __name__ == "__main__":
    unittest.main()
