from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.generate_trading_validation_report import build_report, write_outputs


class TradingValidationReportTest(unittest.TestCase):
    def test_report_validates_mvp_boundary_without_live_claims(self) -> None:
        report = build_report()

        self.assertEqual(report["schema"], "finharness.trading_validation_report.v1")
        self.assertFalse(report["execution_allowed"])
        self.assertFalse(report["validation_result"]["execution_allowed"])
        self.assertEqual(report["evidence_summary"]["fuzz_failed_case_count"], 0)
        self.assertGreater(report["evidence_summary"]["sbom_component_count"], 0)
        self.assertEqual(
            report["validation_result"]["classification"],
            "research_evidence_chain_ready_for_local_paper_or_fake_first_use",
        )
        statuses = {item["claim"]: item["status"] for item in report["claim_ledger"]}
        self.assertEqual(
            statuses["FinHarness has validated profitable trading performance."],
            "not_supported",
        )
        self.assertEqual(
            statuses["FinHarness is ready for autonomous live trading."],
            "rejected",
        )

    def test_report_outputs_are_written(self) -> None:
        report = build_report()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_output = root / "report.json"
            markdown_output = root / "report.md"

            write_outputs(report, json_output, markdown_output)

            self.assertTrue(json_output.exists())
            text = markdown_output.read_text(encoding="utf-8")
            self.assertIn("does not pass as a live trading system", text)
            self.assertIn("Not autonomous live trading approval.", text)


if __name__ == "__main__":
    unittest.main()
