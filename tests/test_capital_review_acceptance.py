from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from scripts.run_capital_review_acceptance import FIXTURE_ROOT, run_acceptance


class CapitalReviewAcceptanceTest(unittest.TestCase):
    def test_canonical_review_blocked_data_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "acceptance"
            summary = run_acceptance(root, now=datetime.now(UTC))
            self.assertTrue(summary["ok"])
            admitted = summary["journeys"]["admitted_review_and_restart"]
            self.assertEqual(admitted["capital_truth_admission"], "admitted")
            self.assertEqual(admitted["position_count"], 2)
            self.assertEqual(admitted["total_assets"], 10000.0)
            self.assertEqual(admitted["decision"], "deferred")
            self.assertTrue(admitted["restart_recovered"])
            self.assertTrue(admitted["replay_reused_identity"])
            blocked = summary["journeys"]["blocked_data"]
            self.assertEqual(blocked["capital_truth_admission"], "blocked")
            self.assertEqual(blocked["evidence_integrity"], "intact")
            self.assertEqual(blocked["candidate_count"], 0)
            self.assertIn("valuation_unpriced", " ".join(blocked["valuation_blockers"]))
            self.assertTrue((root / "admitted" / "state.sqlite").is_file())
            self.assertTrue((root / "blocked" / "state.sqlite").is_file())

    def test_checked_in_fixtures_use_runtime_clocks(self) -> None:
        for name in ("admitted.csv.template", "blocked.csv.template"):
            self.assertIn(
                "{{AS_OF_UTC}}",
                (FIXTURE_ROOT / name).read_text(encoding="utf-8"),
            )
        self.assertIn(
            "{{VALUED_AT_UTC}}",
            (FIXTURE_ROOT / "admitted.csv.template").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
