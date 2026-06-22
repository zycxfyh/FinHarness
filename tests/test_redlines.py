from __future__ import annotations

import unittest

from finharness.redlines import (
    FULL_RESEARCH_REDLINE,
    NARROW_RESEARCH_REDLINE,
    STRUCTURED_ADVICE_KEYS,
    find_nested_redlines,
    reject_text,
)


class RedlineScannerTest(unittest.TestCase):
    def test_wordish_boundaries_allow_market_words(self) -> None:
        self.assertEqual(
            reject_text(
                "Share buyback volume and selloff breadth are historical descriptors.",
                NARROW_RESEARCH_REDLINE,
                surface="test",
            ),
            "Share buyback volume and selloff breadth are historical descriptors.",
        )

    def test_narrow_redline_rejects_advice_execution_language(self) -> None:
        with self.assertRaises(ValueError):
            reject_text("execution plan pending", NARROW_RESEARCH_REDLINE, surface="test")
        with self.assertRaises(ValueError):
            reject_text(
                "model recommendations are favorable",
                NARROW_RESEARCH_REDLINE,
                surface="test",
            )

    def test_nested_scan_checks_keys_and_string_values(self) -> None:
        findings = find_nested_redlines(
            {
                "price_target": 500,
                "details": [{"note": "buy SPY now"}],
            },
            FULL_RESEARCH_REDLINE,
            forbidden_keys=STRUCTURED_ADVICE_KEYS,
        )
        self.assertGreaterEqual(len(findings), 2)
        self.assertIn("$.price_target", {finding.path for finding in findings})
        self.assertIn("$.details[0].note", {finding.path for finding in findings})

    def test_full_redline_rejects_prediction_language(self) -> None:
        with self.assertRaises(ValueError):
            reject_text("expected return unavailable", FULL_RESEARCH_REDLINE, surface="test")


if __name__ == "__main__":
    unittest.main()
