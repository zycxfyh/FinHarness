"""Tests for the fail-closed live-order gate (red-team F1/F3/F4/F5/F7)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from finharness.okx_cli import OkxCliError, OkxCliResult
from finharness.okx_live_gate import (
    LiveOrderBlocked,
    LiveOrderRequest,
    assess_live_order,
    execute_live_order,
    order_notional,
)
from finharness.trading_state_store import (
    TradingStateRecord,
    load_trading_state,
    save_trading_state,
)


def _request(**overrides):
    base = {
        "module": "swap",
        "action": "place",
        "args": ["--instId", "BTC-USDT-SWAP", "--sz", "0.01", "--px", "100"],
        "attester": "operator",
        "reason": "written plan ref docs/plan.md",
        "has_written_thesis": True,
        "max_notional": 50.0,
    }
    base.update(overrides)
    return LiveOrderRequest(**base)


class OkxLiveGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trading-state.json"
        self.addCleanup(self.tmp.cleanup)

    # --- notional parsing -------------------------------------------------

    def test_notional_parsed_from_args(self) -> None:
        self.assertEqual(order_notional(_request()), 1.0)  # 0.01 * 100

    def test_notional_handles_equals_form(self) -> None:
        req = _request(args=["--sz=2", "--px=3"])
        self.assertEqual(order_notional(req), 6.0)

    def test_unbounded_notional_is_none(self) -> None:
        req = _request(args=["--instId", "BTC-USDT-SWAP", "--sz", "0.01"])  # no price
        self.assertIsNone(order_notional(req))

    # --- assess (pure decision) ------------------------------------------

    def test_clean_state_allows(self) -> None:
        decision = assess_live_order(_request(), state_path=self.path)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.guard_level, "clear")

    def test_hard_stop_blocks(self) -> None:
        save_trading_state(
            TradingStateRecord(drawdown_pct=-5.0, consecutive_losses=4), self.path
        )
        decision = assess_live_order(_request(), state_path=self.path)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.guard_level, "hard_stop")

    def test_behavior_reset_flag_blocks(self) -> None:
        save_trading_state(
            TradingStateRecord(behavior_reset_required=True, behavior_reset_reason="x"),
            self.path,
        )
        decision = assess_live_order(_request(), state_path=self.path)
        self.assertFalse(decision.allowed)
        self.assertTrue(any("behavior_reset_required" in r for r in decision.blocking_reasons))

    def test_over_cap_notional_blocks(self) -> None:
        req = _request(args=["--sz", "1000", "--px", "100"])  # 100000 > 50
        decision = assess_live_order(req, state_path=self.path)
        self.assertFalse(decision.allowed)
        self.assertTrue(any("exceeds cap" in r for r in decision.blocking_reasons))

    def test_unbounded_notional_blocks_fail_closed(self) -> None:
        req = _request(args=["--instId", "BTC-USDT-SWAP", "--sz", "0.01"])
        decision = assess_live_order(req, state_path=self.path)
        self.assertFalse(decision.allowed)

    def test_missing_attestation_blocks(self) -> None:
        decision = assess_live_order(_request(attester="", reason=""), state_path=self.path)
        self.assertFalse(decision.allowed)

    def test_no_thesis_blocks_via_guard_caution(self) -> None:
        decision = assess_live_order(
            _request(has_written_thesis=False), state_path=self.path
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.guard_level, "caution")

    # --- execute (gated mutation) ----------------------------------------

    def test_blocked_execute_writes_receipt_and_never_calls_okx(self) -> None:
        save_trading_state(
            TradingStateRecord(drawdown_pct=-5.0, consecutive_losses=4), self.path
        )
        receipt_root = Path(self.tmp.name) / "receipts"
        with mock.patch("finharness.okx_live_gate.LIVE_ORDER_RECEIPT_ROOT", receipt_root), \
             mock.patch("finharness.okx_live_gate.run_okx_live_mutation_command") as run, \
             self.assertRaises(LiveOrderBlocked):
            execute_live_order(_request(), state_path=self.path)
        run.assert_not_called()
        receipts = list(receipt_root.glob("*.json"))
        self.assertEqual(len(receipts), 1)
        payload = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["outcome"], "blocked")
        # a blocked attempt must not record a trade
        self.assertEqual(load_trading_state(self.path).trades_recorded, 0)

    def test_allowed_execute_writes_receipt_and_updates_state(self) -> None:
        receipt_root = Path(self.tmp.name) / "receipts"
        fake = OkxCliResult(module="swap", action="place", command=["okx"], data={"ordId": "1"})
        with mock.patch("finharness.okx_live_gate.LIVE_ORDER_RECEIPT_ROOT", receipt_root), \
             mock.patch(
                 "finharness.okx_live_gate.run_okx_live_mutation_command",
                 return_value=fake,
             ) as run:
            result = execute_live_order(_request(), state_path=self.path)
            run.assert_called_once()
        self.assertIn("receipt_ref", result)
        payload = json.loads(list(receipt_root.glob("*.json"))[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["outcome"], "executed")
        # F5: the placed order updated persisted state
        self.assertEqual(load_trading_state(self.path).trades_recorded, 1)

    def test_okx_error_writes_error_receipt_and_no_state_update(self) -> None:
        receipt_root = Path(self.tmp.name) / "receipts"
        with mock.patch("finharness.okx_live_gate.LIVE_ORDER_RECEIPT_ROOT", receipt_root), \
             mock.patch(
                 "finharness.okx_live_gate.run_okx_live_mutation_command",
                 side_effect=OkxCliError("boom"),
             ), self.assertRaises(OkxCliError):
            execute_live_order(_request(), state_path=self.path)
        payload = json.loads(list(receipt_root.glob("*.json"))[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["outcome"], "error")
        self.assertEqual(load_trading_state(self.path).trades_recorded, 0)


if __name__ == "__main__":
    unittest.main()
