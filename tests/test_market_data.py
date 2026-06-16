from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from finharness.market_data import (
    DEFAULT_DATA_BIAS_CONTROLS,
    ROOT,
    MarketDataQuality,
    SourceSpec,
    build_ohlcv_snapshot_from_history,
    build_quality_report,
    ohlcv_to_nautilus_bars,
    reconcile_close,
    write_nautilus_catalog,
)


def sample_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-01-02", "2026-01-03"], utc=True),
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.5],
            "close": [101.0, 102.5],
            "volume": [1000, 1200],
        }
    )


class MarketDataGovernanceTest(unittest.TestCase):
    def test_quality_report_accepts_clean_ohlcv(self) -> None:
        report = build_quality_report(
            sample_ohlcv(),
            required_columns=["date", "open", "high", "low", "close", "volume"],
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.outlier_flags, [])
        self.assertEqual(report.duplicate_timestamps, 0)

    def test_quality_report_catches_duplicate_timestamps(self) -> None:
        frame = pd.concat([sample_ohlcv(), sample_ohlcv().iloc[[0]]], ignore_index=True)

        report = build_quality_report(
            frame,
            required_columns=["date", "open", "high", "low", "close", "volume"],
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.duplicate_timestamps, 1)

    def test_quality_report_flags_high_below_low(self) -> None:
        frame = sample_ohlcv()
        frame.loc[0, "high"] = 98.0

        report = build_quality_report(
            frame,
            required_columns=["date", "open", "high", "low", "close", "volume"],
        )

        self.assertFalse(report.ok)
        self.assertIn("high_below_low", report.outlier_flags)

    def test_quality_report_flags_non_positive_ohlc(self) -> None:
        frame = sample_ohlcv()
        frame.loc[0, "close"] = 0.0

        report = build_quality_report(
            frame,
            required_columns=["date", "open", "high", "low", "close", "volume"],
        )

        self.assertFalse(report.ok)
        self.assertIn("close_non_positive", report.outlier_flags)

    def test_quality_report_records_null_counts(self) -> None:
        frame = sample_ohlcv()
        frame.loc[0, "volume"] = None

        report = build_quality_report(
            frame,
            required_columns=["date", "open", "high", "low", "close", "volume"],
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.null_counts["volume"], 1)

    def test_quality_report_records_reconciliation_without_blocking(self) -> None:
        reconciliation = {
            "status": "single_source_unreconciled",
            "reason": "unit test",
        }

        report = build_quality_report(
            sample_ohlcv(),
            required_columns=["date", "open", "high", "low", "close", "volume"],
            reconciliation=reconciliation,
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.reconciliation, reconciliation)
        self.assertTrue(
            any("single_source_unreconciled" in note for note in report.notes)
        )

    def test_quality_report_records_ohlc_nulls_without_outlier_flag(self) -> None:
        frame = sample_ohlcv()
        frame.loc[0, "close"] = None

        report = build_quality_report(
            frame,
            required_columns=["date", "open", "high", "low", "close", "volume"],
        )

        self.assertTrue(report.ok)
        self.assertEqual(report.null_counts["close"], 1)
        self.assertNotIn("close_non_positive", report.outlier_flags)

    def test_quality_report_marks_stale_without_forcing_failure(self) -> None:
        frame = sample_ohlcv()
        frame["date"] = [
            datetime.now(UTC) - timedelta(days=10),
            datetime.now(UTC) - timedelta(days=9),
        ]

        report = build_quality_report(
            frame,
            required_columns=["date", "open", "high", "low", "close", "volume"],
            max_staleness_days=3,
        )

        self.assertTrue(report.ok)
        self.assertTrue(report.stale)
        self.assertTrue(any("latest bar is" in note for note in report.notes))

    def test_market_data_quality_has_no_execution_authority_field(self) -> None:
        report = build_quality_report(
            sample_ohlcv(),
            required_columns=["date", "open", "high", "low", "close", "volume"],
        )

        self.assertFalse(hasattr(report, "execution_allowed"))
        self.assertNotIn("execution_allowed", MarketDataQuality.model_fields)

    def test_ohlcv_converts_to_nautilus_bars_and_catalog(self) -> None:
        bars = ohlcv_to_nautilus_bars(sample_ohlcv(), symbol="SPY")

        self.assertEqual(len(bars), 2)
        self.assertEqual(str(bars[0].bar_type), "SPY.YFINANCE-1-DAY-LAST-EXTERNAL")

        with tempfile.TemporaryDirectory() as directory:
            catalog_ref = write_nautilus_catalog(bars, catalog_root=Path(directory))
            catalog = ParquetDataCatalog(directory)

            self.assertEqual(catalog_ref, directory)
            self.assertEqual(len(catalog.bars(bar_types=[bars[0].bar_type])), 2)

    def test_snapshot_receipt_records_all_eight_layers(self) -> None:
        receipt = build_ohlcv_snapshot_from_history(
            sample_ohlcv(),
            symbol="SPY",
            source=SourceSpec(
                provider="yfinance",
                upstream_source="Yahoo Finance",
                asset_class="equity",
                dataset="ohlcv_history",
                access_method="api_pull",
                wheel="yfinance",
                wheel_version="test",
                adjustment="auto_adjust",
            ),
            fetch_config={
                "symbol": "SPY",
                "adjustment": "auto_adjust",
                "auto_adjust": True,
            },
            raw_payload={"rows": 2},
            adjusted=True,
            adjustment="auto_adjust",
            write_catalog=False,
        )

        expected_layers = {
            "source",
            "ingestion",
            "normalization",
            "quality",
            "storage",
            "snapshot",
            "lineage",
            "consumer",
        }
        self.assertEqual(set(receipt.eight_layer_map), expected_layers)
        self.assertTrue(receipt.snapshot.quality.ok)
        self.assertEqual(receipt.snapshot.lineage.quality_backend, "pandera")
        self.assertIsNotNone(receipt.snapshot.lineage.quality_backend_version)
        self.assertTrue(receipt.snapshot.adjusted)
        self.assertEqual(receipt.snapshot.lineage.source.adjustment, "auto_adjust")
        self.assertEqual(
            receipt.snapshot.lineage.fetch_config["adjustment"],
            "auto_adjust",
        )
        self.assertEqual(
            receipt.snapshot.lineage.data_bias_controls,
            DEFAULT_DATA_BIAS_CONTROLS,
        )

        receipt_path = ROOT / receipt.snapshot.receipt_ref
        saved = json.loads(receipt_path.read_text())
        self.assertEqual(saved["snapshot"]["snapshot_id"], receipt.snapshot.snapshot_id)
        self.assertEqual(saved["snapshot"]["lineage"]["quality_backend"], "pandera")
        self.assertIsNotNone(saved["snapshot"]["lineage"]["quality_backend_version"])

    def test_snapshot_survives_nautilus_catalog_overlap(self) -> None:
        with patch(
            "finharness.market_data.write_nautilus_catalog",
            side_effect=ValueError("would create non-disjoint intervals"),
        ):
            receipt = build_ohlcv_snapshot_from_history(
                sample_ohlcv(),
                symbol="SPY",
                source=SourceSpec(
                    provider="yfinance",
                    upstream_source="Yahoo Finance",
                    asset_class="equity",
                    dataset="ohlcv_history",
                    access_method="api_pull",
                    wheel="yfinance",
                    wheel_version="test",
                ),
                fetch_config={"symbol": "SPY"},
                raw_payload={"rows": 2},
                adjusted=False,
                write_catalog=True,
            )

        self.assertTrue(receipt.snapshot.quality.ok)
        self.assertIsNone(receipt.snapshot.lineage.catalog_ref)
        self.assertTrue(
            any(
                "nautilus catalog write skipped" in note
                for note in receipt.snapshot.quality.notes
            )
        )

    def test_reconcile_close_records_second_source_divergence(self) -> None:
        def second_provider(symbol: str, start: str, end: str, *, adjustment: str):
            self.assertEqual(symbol, "SPY")
            self.assertEqual(start, "2026-01-01")
            self.assertEqual(end, "2026-01-05")
            self.assertEqual(adjustment, "auto_adjust")
            secondary = sample_ohlcv()
            secondary.loc[1, "close"] = 103.525
            return secondary

        reconciliation = reconcile_close(
            "SPY",
            "2026-01-01",
            "2026-01-05",
            primary_history=sample_ohlcv(),
            second_provider=second_provider,
            adjustment="auto_adjust",
        )

        self.assertEqual(reconciliation["status"], "reconciled")
        self.assertEqual(reconciliation["overlap_rows"], 2)
        self.assertAlmostEqual(reconciliation["max_close_divergence_pct"], 1.0)

    def test_reconcile_close_fails_open_to_single_source_disclosure(self) -> None:
        def failing_provider(symbol: str, start: str, end: str, *, adjustment: str):
            raise RuntimeError("offline")

        reconciliation = reconcile_close(
            "SPY",
            "2026-01-01",
            "2026-01-05",
            primary_history=sample_ohlcv(),
            second_provider=failing_provider,
            adjustment="auto_adjust",
        )

        self.assertEqual(reconciliation["status"], "single_source_unreconciled")
        self.assertIn("second provider unavailable", reconciliation["reason"])


if __name__ == "__main__":
    unittest.main()
