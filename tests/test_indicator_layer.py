from __future__ import annotations

import json
import unittest
from pathlib import Path

import pandas as pd

from finharness.indicator_layer import (
    build_indicator_quality,
    build_indicator_snapshot,
    compute_library_core_indicators,
    compute_ohlcv_risk_return_features,
)
from finharness.market_data import SourceSpec, build_ohlcv_snapshot_from_history


def sample_history(rows: int = 90) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": f"2026-01-{index % 28 + 1:02d}",
                "open": 100.0 + index * 0.2,
                "high": 101.0 + index * 0.2,
                "low": 99.0 + index * 0.2,
                "close": 100.5 + index * 0.2,
                "volume": 1_000_000 + index,
            }
            for index in range(rows)
        ]
    )


class IndicatorLayerTest(unittest.TestCase):
    def test_core_indicators_are_library_backed(self) -> None:
        features, specs = compute_library_core_indicators(sample_history())

        self.assertIn("macd", features.columns)
        self.assertIn("rsi", features.columns)
        self.assertIn("bb_percent_b", features.columns)
        self.assertIn("atr", features.columns)
        self.assertIn("simple_return", features.columns)
        self.assertIn("max_drawdown_to_date", features.columns)
        self.assertIn("rolling_var_95_20d", features.columns)
        self.assertEqual({spec.library for spec in specs}, {"TA-Lib", "pandas-ta", "pandas/numpy"})

    def test_risk_return_features_describe_ohlcv_history(self) -> None:
        history = pd.DataFrame(
            [
                {
                    "date": f"2026-01-{index + 1:02d}",
                    "open": price,
                    "high": price + 1,
                    "low": price - 1,
                    "close": price,
                    "volume": 1_000_000,
                }
                for index, price in enumerate(
                    [100.0, 110.0, 90.0, 120.0] + [121.0 + i for i in range(30)]
                )
            ]
        )

        features = compute_ohlcv_risk_return_features(history)

        self.assertAlmostEqual(features["simple_return"].iloc[1], 0.1)
        self.assertAlmostEqual(features["log_return"].iloc[1], 0.0953101798)
        self.assertAlmostEqual(features["wealth_index"].iloc[-1], history["close"].iloc[-1] / 100.0)
        self.assertAlmostEqual(features["max_drawdown_to_date"].iloc[2], -0.1818181818)
        self.assertGreater(features["drawdown_duration"].iloc[2], 0)
        self.assertFalse(pd.isna(features["rolling_var_95_20d"].iloc[-1]))

    def test_quality_report_blocks_latest_null_features(self) -> None:
        features, _ = compute_library_core_indicators(sample_history(rows=5))

        quality = build_indicator_quality(features)

        self.assertFalse(quality.ok)
        self.assertIn("ma_slow", quality.latest_null_features)

    def test_indicator_receipt_links_to_first_layer_snapshot(self) -> None:
        history = sample_history()
        data_receipt = build_ohlcv_snapshot_from_history(
            history,
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
            raw_payload={"rows": len(history)},
            adjusted=False,
            write_catalog=False,
        )

        indicator_receipt = build_indicator_snapshot(
            symbol="SPY",
            history=history,
            market_data_snapshot=data_receipt.snapshot,
        )

        self.assertTrue(indicator_receipt.snapshot.quality.ok)
        self.assertFalse(indicator_receipt.snapshot.execution_allowed)
        self.assertEqual(
            indicator_receipt.snapshot.lineage.input_snapshot_id,
            data_receipt.snapshot.snapshot_id,
        )
        self.assertEqual(
            set(indicator_receipt.stage_flow),
            {
                "initiation",
                "planning",
                "preparation",
                "execution",
                "monitoring",
                "closing",
                "documentation",
                "retrospective",
            },
        )

        receipt_path = Path("/root/projects/finharness") / indicator_receipt.snapshot.receipt_ref
        saved = json.loads(receipt_path.read_text())
        self.assertEqual(
            saved["snapshot"]["indicator_snapshot_id"],
            indicator_receipt.snapshot.indicator_snapshot_id,
        )


if __name__ == "__main__":
    unittest.main()
