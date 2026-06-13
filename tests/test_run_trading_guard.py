from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from scripts import run_trading_guard

from finharness.trading_guard import GuardThresholds
from finharness.trading_state_store import TradingStateRecord


class RunTradingGuardScriptTests(unittest.TestCase):
    def test_uses_effective_thresholds_with_provenance(self) -> None:
        stdout = io.StringIO()
        thresholds = GuardThresholds(min_minutes_between_trades_after_loss=45)

        with (
            mock.patch(
                "scripts.run_trading_guard.load_trading_state",
                return_value=TradingStateRecord(),
            ),
            mock.patch(
                "scripts.run_trading_guard.resolve_guard_thresholds",
                return_value=(
                    thresholds,
                    {"min_minutes_between_trades_after_loss": "rulechg_test"},
                    [],
                ),
            ),
            redirect_stdout(stdout),
        ):
            code = run_trading_guard.main(
                [
                    "--consecutive-losses",
                    "1",
                    "--minutes-since-last-trade",
                    "40",
                    "--thesis",
                ]
            )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(payload["level"], "caution")
        self.assertFalse(payload["trade_allowed"])
        self.assertEqual(
            payload["effective_thresholds"]["min_minutes_between_trades_after_loss"],
            45,
        )
        self.assertEqual(
            payload["threshold_provenance"]["min_minutes_between_trades_after_loss"],
            "rulechg_test",
        )
        self.assertTrue(any("minimum is 45" in reason for reason in payload["reasons"]))


if __name__ == "__main__":
    unittest.main()
