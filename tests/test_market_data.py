from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from nautilus_trader.persistence.catalog import ParquetDataCatalog

from finharness.market_data import (
    SourceSpec,
    build_ohlcv_snapshot_from_history,
    build_quality_report,
    ohlcv_to_nautilus_bars,
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
    def test_quality_report_catches_duplicate_timestamps(self) -> None:
        frame = pd.concat([sample_ohlcv(), sample_ohlcv().iloc[[0]]], ignore_index=True)

        report = build_quality_report(
            frame,
            required_columns=["date", "open", "high", "low", "close", "volume"],
        )

        self.assertFalse(report.ok)
        self.assertEqual(report.duplicate_timestamps, 1)

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
            ),
            fetch_config={"symbol": "SPY"},
            raw_payload={"rows": 2},
            adjusted=False,
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

        receipt_path = Path("/root/projects/finharness") / receipt.snapshot.receipt_ref
        saved = json.loads(receipt_path.read_text())
        self.assertEqual(saved["snapshot"]["snapshot_id"], receipt.snapshot.snapshot_id)


if __name__ == "__main__":
    unittest.main()
