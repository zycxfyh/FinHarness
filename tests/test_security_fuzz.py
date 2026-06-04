from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.run_fuzz_baseline import build_fuzz_report, write_report


class SecurityFuzzBaselineTest(unittest.TestCase):
    def test_fuzz_baseline_passes_governance_invariants(self) -> None:
        report = build_fuzz_report(seed=20260604, generated_count=4)

        self.assertEqual(report["schema"], "finharness.fuzz_baseline.v1")
        self.assertFalse(report["execution_allowed"])
        self.assertEqual(report["failed_case_count"], 0)
        self.assertGreaterEqual(report["case_count"], 12)
        self.assertEqual(
            set(report["targets"]),
            {"research_assets", "security_surface", "trading_guard"},
        )

    def test_fuzz_report_is_json_serializable(self) -> None:
        report = build_fuzz_report(seed=7, generated_count=1)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "fuzz-report.json"
            write_report(output, report)

            self.assertTrue(output.exists())
            self.assertIn("local_baseline_not_oss_fuzz", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
