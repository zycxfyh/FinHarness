"""Tests for H3: the real realized-move disconfirming check."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.validation_metrics import assess_realized_move, load_cached_close_series


class AssessRealizedMoveTests(unittest.TestCase):
    def test_too_few_prices_is_not_testable(self) -> None:
        out = assess_realized_move([100.0])
        self.assertEqual(out["verdict"], "not_testable")
        self.assertFalse(out["testable"])

    def test_flat_series_weakens_hypothesis(self) -> None:
        # A predicted reaction that never shows up in the prices weakens it.
        out = assess_realized_move([100.0, 100.2, 99.9, 100.1], move_floor=0.01)
        self.assertEqual(out["verdict"], "weakened")
        self.assertTrue(out["weakens"])
        self.assertIn("total_return", out["metrics"])

    def test_material_move_is_inconclusive_never_supported(self) -> None:
        out = assess_realized_move([100.0, 110.0, 120.0], move_floor=0.01)
        self.assertEqual(out["verdict"], "inconclusive")
        self.assertFalse(out["weakens"])
        # Real metrics are reported.
        self.assertAlmostEqual(out["metrics"]["total_return"], 0.2, places=6)


class LoadCachedCloseSeriesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def test_missing_cache_returns_none(self) -> None:
        self.assertIsNone(load_cached_close_series("NVDA", cache_dir=self.cache))

    def test_reads_close_column(self) -> None:
        (self.cache / "spy_history.csv").write_text(
            "date,open,high,low,close,volume\n"
            "2025-01-02,100,101,99,100.5,1000\n"
            "2025-01-03,100.5,102,100,101.5,1100\n",
            encoding="utf-8",
        )
        closes = load_cached_close_series("SPY", cache_dir=self.cache)
        self.assertEqual(closes, [100.5, 101.5])


if __name__ == "__main__":
    unittest.main()
