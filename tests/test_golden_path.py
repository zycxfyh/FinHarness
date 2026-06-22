from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.run_golden_path import replay_chain, run_golden_path


class GoldenPathHappyTest(unittest.TestCase):
    """Offline end-to-end: the real CI anchor that the whole loop runs and replays."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.summary = run_golden_path(Path(self.tmp.name))
        self.addCleanup(self.tmp.cleanup)

    def test_two_candidates_both_detectors(self) -> None:
        self.assertGreaterEqual(self.summary["proposals"], 2)
        self.assertEqual(
            set(self.summary["detector_kinds"]) & {"concentration_high", "cash_buffer_low"},
            {"concentration_high", "cash_buffer_low"},
        )

    def test_compare_leg_really_exercised(self) -> None:
        self.assertGreaterEqual(self.summary["compare_pairs"], 1)
        self.assertGreaterEqual(self.summary["timeline_entries"], 3)  # attest+annotation+compare

    def test_chain_replays_and_carries_no_execution(self) -> None:
        # CI happy path MUST be replayed:true — a broken chain may not pass silently.
        self.assertTrue(self.summary["replayed"], self.summary["replay_gaps"])
        self.assertEqual(self.summary["replay_gaps"], [])
        self.assertFalse(self.summary["execution_allowed"])

    def test_summary_is_bounded(self) -> None:
        # Structural bound: only an allowlisted, shallow set of counts / refs / flags — no
        # nested dicts and no raw numeric ledger values (which would carry amounts/PII).
        allowed = {
            "ok", "proposals", "detector_kinds", "compare_pairs", "timeline_entries",
            "proposal_receipt_ref", "review_event_receipt_ref", "replayed", "replay_gaps",
            "artifact_root", "cleanup_hint", "execution_allowed",
        }
        self.assertEqual(set(self.summary), allowed)
        for value in self.summary.values():
            self.assertNotIsInstance(value, dict)  # no nested ledger payload
            self.assertNotIsInstance(value, float)  # counts are ints; no money floats
            if isinstance(value, list):
                self.assertTrue(all(isinstance(item, str) for item in value))


class GoldenPathFaultInjectionTest(unittest.TestCase):
    def test_missing_proposal_receipt_fails_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_golden_path(Path(tmp))
            self.assertTrue(summary["replayed"])  # baseline: intact chain replays
            # Delete the proposal receipt file, then re-run the replay verifier.
            Path(summary["proposal_receipt_ref"]).unlink()
            gaps = replay_chain(
                summary["proposal_receipt_ref"], summary["review_event_receipt_ref"]
            )
            self.assertTrue(gaps)  # a deleted receipt -> replayed:false signal

    def test_missing_review_event_receipt_fails_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = run_golden_path(Path(tmp))
            Path(summary["review_event_receipt_ref"]).unlink()
            gaps = replay_chain(
                summary["proposal_receipt_ref"], summary["review_event_receipt_ref"]
            )
            self.assertTrue(any("receipt file missing" in gap for gap in gaps))


if __name__ == "__main__":
    unittest.main()
