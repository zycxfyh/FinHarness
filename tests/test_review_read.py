from __future__ import annotations

import unittest

from finharness.review_read import read_proposal_timeline
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


if __name__ == "__main__":
    unittest.main()
