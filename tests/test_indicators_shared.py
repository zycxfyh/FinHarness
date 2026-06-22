from __future__ import annotations

import unittest

import pandas as pd

from finharness.indicators.shared import REQUIRED_OHLCV, validate_ohlcv


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


class OhlcvStrictValidationTest(unittest.TestCase):
    def test_missing_columns_error_message_is_stable(self) -> None:
        frame = valid_ohlcv().drop(columns=["volume"])

        with self.assertRaisesRegex(
            ValueError,
            r"OHLCV data missing columns: \['volume'\]",
        ):
            validate_ohlcv(frame)

    def test_empty_frame_error_message_is_stable(self) -> None:
        with self.assertRaisesRegex(ValueError, "OHLCV data is empty"):
            validate_ohlcv(valid_ohlcv().iloc[0:0])

    def test_non_numeric_ohlc_error_message_is_stable(self) -> None:
        frame = valid_ohlcv()
        frame["close"] = frame["close"].astype(object)
        frame.loc[0, "close"] = "bad"

        with self.assertRaisesRegex(ValueError, "OHLC data contains non-numeric values"):
            validate_ohlcv(frame)

    def test_non_positive_ohlc_error_message_is_stable(self) -> None:
        frame = valid_ohlcv()
        frame.loc[0, "low"] = 0.0

        with self.assertRaisesRegex(ValueError, "OHLC prices must be positive"):
            validate_ohlcv(frame)

    def test_happy_path_returns_required_columns_with_numeric_prices(self) -> None:
        result = validate_ohlcv(valid_ohlcv())

        self.assertEqual(list(result.columns), REQUIRED_OHLCV)
        for column in ["open", "high", "low", "close", "volume"]:
            self.assertTrue(pd.api.types.is_numeric_dtype(result[column]))

    def test_volume_nan_currently_passes_strict_validation(self) -> None:
        frame = valid_ohlcv()
        frame.loc[0, "volume"] = None

        result = validate_ohlcv(frame)

        self.assertTrue(pd.isna(result.loc[0, "volume"]))


if __name__ == "__main__":
    unittest.main()
