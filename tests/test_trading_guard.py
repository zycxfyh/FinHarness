from __future__ import annotations

import unittest

from finharness.trading_guard import TradingState, evaluate_trading_state


class TradingGuardTest(unittest.TestCase):
    def test_hard_stops_large_drawdown(self) -> None:
        decision = evaluate_trading_state(
            TradingState(
                drawdown_pct=-4.2,
                consecutive_losses=1,
                planned_trade_has_written_thesis=True,
            )
        )
        self.assertEqual(decision.level, "hard_stop")
        self.assertFalse(decision.trade_allowed)

    def test_hard_stops_consecutive_losses(self) -> None:
        decision = evaluate_trading_state(
            TradingState(
                drawdown_pct=-0.5,
                consecutive_losses=3,
                planned_trade_has_written_thesis=True,
            )
        )
        self.assertEqual(decision.level, "hard_stop")
        self.assertFalse(decision.trade_allowed)

    def test_requires_written_thesis(self) -> None:
        decision = evaluate_trading_state(
            TradingState(
                drawdown_pct=0.0,
                consecutive_losses=0,
                planned_trade_has_written_thesis=False,
            )
        )
        self.assertEqual(decision.level, "caution")
        self.assertFalse(decision.trade_allowed)

    def test_clear_when_limits_and_process_are_ok(self) -> None:
        decision = evaluate_trading_state(
            TradingState(
                drawdown_pct=0.1,
                consecutive_losses=0,
                planned_trade_has_written_thesis=True,
            )
        )
        self.assertEqual(decision.level, "clear")
        self.assertTrue(decision.trade_allowed)


if __name__ == "__main__":
    unittest.main()
