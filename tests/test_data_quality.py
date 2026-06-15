from __future__ import annotations

import unittest

import pandas as pd
import pandera.pandas as pa

import finharness.data_quality as data_quality
from finharness.data_quality import (
    DATA_QUALITY_BACKEND,
    OHLCV_STRICT_SCHEMA,
    REQUIRED_OHLCV,
    data_quality_backend_version,
    price_outlier_flags,
    validate_ohlcv_strict,
)
from finharness.market_data import build_quality_report


def valid_ohlcv() -> pd.DataFrame:
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


class DataQualityPanderaAdapterTest(unittest.TestCase):
    def test_schema_backend_is_pandera(self) -> None:
        self.assertIsInstance(OHLCV_STRICT_SCHEMA, pa.DataFrameSchema)
        self.assertEqual(DATA_QUALITY_BACKEND, "pandera")
        self.assertIsNotNone(data_quality_backend_version())

    def test_strict_path_preserves_missing_columns_message(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            r"OHLCV data missing columns: \['volume'\]",
        ):
            validate_ohlcv_strict(valid_ohlcv().drop(columns=["volume"]))

    def test_strict_path_preserves_empty_frame_message(self) -> None:
        with self.assertRaisesRegex(ValueError, "OHLCV data is empty"):
            validate_ohlcv_strict(valid_ohlcv().iloc[0:0])

    def test_strict_path_preserves_non_numeric_ohlc_message(self) -> None:
        frame = valid_ohlcv()
        frame["close"] = frame["close"].astype(object)
        frame.loc[0, "close"] = "bad"

        with self.assertRaisesRegex(ValueError, "OHLC data contains non-numeric values"):
            validate_ohlcv_strict(frame)

    def test_strict_path_preserves_positive_price_message(self) -> None:
        frame = valid_ohlcv()
        frame.loc[0, "low"] = -1.0

        with self.assertRaisesRegex(ValueError, "OHLC prices must be positive"):
            validate_ohlcv_strict(frame)

    def test_strict_path_returns_required_columns_with_numeric_dtypes(self) -> None:
        result = validate_ohlcv_strict(valid_ohlcv())

        self.assertEqual(list(result.columns), REQUIRED_OHLCV)
        for column in ["open", "high", "low", "close", "volume"]:
            self.assertTrue(pd.api.types.is_numeric_dtype(result[column]))

    def test_strict_path_accepts_integer_ohlc_prices(self) -> None:
        frame = pd.DataFrame(
            {
                "date": ["2026-01-02", "2026-01-03"],
                "open": [100, 101],
                "high": [102, 103],
                "low": [99, 100],
                "close": [101, 102],
                "volume": [1000, 1200],
            }
        )

        result = validate_ohlcv_strict(frame)

        self.assertEqual(list(result.columns), REQUIRED_OHLCV)
        self.assertTrue(pd.api.types.is_float_dtype(result["open"]))

    def test_volume_nan_passes_strict_path(self) -> None:
        frame = valid_ohlcv()
        frame.loc[0, "volume"] = None

        result = validate_ohlcv_strict(frame)

        self.assertTrue(pd.isna(result.loc[0, "volume"]))

    def test_price_outlier_flags_use_locked_order(self) -> None:
        flags = price_outlier_flags(
            pd.DataFrame(
                {
                    "open": [100.0],
                    "high": [98.0],
                    "low": [99.0],
                    "close": [-1.0],
                }
            )
        )

        self.assertEqual(flags, ["close_non_positive", "high_below_low"])

    def test_price_outlier_flags_ignore_missing_prices(self) -> None:
        flags = price_outlier_flags(
            pd.DataFrame(
                {
                    "open": [100.0],
                    "high": [102.0],
                    "low": [99.0],
                    "close": [None],
                }
            )
        )

        self.assertEqual(flags, [])

    def test_data_quality_layer_has_no_execution_authority(self) -> None:
        self.assertFalse(hasattr(data_quality, "execution_allowed"))
        report = build_quality_report(
            valid_ohlcv(),
            required_columns=["date", "open", "high", "low", "close", "volume"],
        )
        self.assertFalse(hasattr(report, "execution_allowed"))


if __name__ == "__main__":
    unittest.main()
