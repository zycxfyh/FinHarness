from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from finharness.data_entry import fetch_yfinance_history


def raw_yfinance_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.5],
            "Close": [101.0, 102.5],
            "Volume": [1000, 1200],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-03"]),
    )


class DataEntryTest(unittest.TestCase):
    def test_fetch_yfinance_history_defaults_to_auto_adjust(self) -> None:
        with patch(
            "finharness.data_entry.yf.download",
            return_value=raw_yfinance_frame(),
        ) as download:
            history = fetch_yfinance_history("SPY", "2026-01-01", "2026-01-05")

        # G02 migration: historical prices now request corporate-action adjustment.
        self.assertTrue(download.call_args.kwargs["auto_adjust"])
        self.assertEqual(list(history.columns), ["date", "open", "high", "low", "close", "volume"])
        self.assertEqual(len(history), 2)

    def test_fetch_yfinance_history_can_explicitly_request_raw_prices(self) -> None:
        with patch(
            "finharness.data_entry.yf.download",
            return_value=raw_yfinance_frame(),
        ) as download:
            fetch_yfinance_history(
                "SPY",
                "2026-01-01",
                "2026-01-05",
                adjustment="raw",
            )

        self.assertFalse(download.call_args.kwargs["auto_adjust"])


if __name__ == "__main__":
    unittest.main()
