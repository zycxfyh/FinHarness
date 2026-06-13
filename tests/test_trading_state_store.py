"""Tests for the persistent trading state store (Loop 3 feedback edge)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.trading_state_store import (
    TradingStateRecord,
    load_trading_state,
    merge_into_risk_context,
    record_operator_outcome,
    reset_behavior_flag,
    save_trading_state,
    update_from_post_trade_snapshot,
)


class TradingStateStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trading-state.json"
        self.addCleanup(self.tmp.cleanup)

    def test_missing_file_yields_safe_defaults(self) -> None:
        record = load_trading_state(self.path)
        self.assertEqual(record.consecutive_losses, 0)
        self.assertEqual(record.drawdown_pct, 0.0)
        self.assertFalse(record.behavior_reset_required)

    def test_corrupt_file_fails_closed(self) -> None:
        self.path.write_text("{not json", encoding="utf-8")
        record = load_trading_state(self.path)
        self.assertTrue(record.behavior_reset_required)
        self.assertIn("unreadable", record.behavior_reset_reason or "")

    def test_save_and_load_round_trip(self) -> None:
        record = TradingStateRecord(drawdown_pct=-1.2, consecutive_losses=2)
        save_trading_state(record, self.path)
        loaded = load_trading_state(self.path)
        self.assertEqual(loaded.drawdown_pct, -1.2)
        self.assertEqual(loaded.consecutive_losses, 2)

    def test_operator_loss_increments_and_win_resets(self) -> None:
        record_operator_outcome(
            outcome="loss", drawdown_pct=-1.0, receipt_ref="r1", path=self.path
        )
        second = record_operator_outcome(
            outcome="loss", drawdown_pct=-2.0, receipt_ref="r2", path=self.path
        )
        self.assertEqual(second.consecutive_losses, 2)
        self.assertEqual(second.drawdown_pct, -2.0)
        third = record_operator_outcome(
            outcome="win", drawdown_pct=-0.5, receipt_ref="r3", path=self.path
        )
        self.assertEqual(third.consecutive_losses, 0)
        self.assertEqual(third.trades_recorded, 3)
        self.assertEqual(third.source_refs, ["r1", "r2", "r3"])

    def test_post_trade_snapshot_records_trade_but_never_invents_loss(self) -> None:
        updated = update_from_post_trade_snapshot(
            {"final_status": "reconciled_filled", "receipt_ref": "pt1"},
            path=self.path,
        )
        self.assertEqual(updated.trades_recorded, 1)
        self.assertEqual(updated.consecutive_losses, 0)
        self.assertIsNotNone(updated.last_trade_at_utc)
        self.assertFalse(updated.behavior_reset_required)

    def test_process_failure_trips_behavior_reset(self) -> None:
        updated = update_from_post_trade_snapshot(
            {"final_status": "lineage_failed", "receipt_ref": "pt2"},
            path=self.path,
        )
        self.assertTrue(updated.behavior_reset_required)
        self.assertIn("lineage_failed", updated.behavior_reset_reason or "")
        cleared = reset_behavior_flag(reason="reviewed receipts pt2", path=self.path)
        self.assertFalse(cleared.behavior_reset_required)
        self.assertTrue(any("reviewed receipts" in note for note in cleared.notes))

    def test_merge_is_conservative_explicit_keys_cannot_weaken_state(self) -> None:
        # Red-team F6 (2026-06-13): a hand-fed clean context must not erase
        # persisted protective state. Persisted state is a floor, not a default.
        save_trading_state(
            TradingStateRecord(
                drawdown_pct=-3.5,
                consecutive_losses=3,
                behavior_reset_required=True,
            ),
            self.path,
        )
        merged = merge_into_risk_context(
            {
                "drawdown_pct": -0.1,
                "consecutive_losses": 0,
                "behavior_reset_required": False,
            },
            path=self.path,
        )
        # The worse persisted values win; the clean hand-fed values are ignored.
        self.assertEqual(merged["drawdown_pct"], -3.5)
        self.assertEqual(merged["consecutive_losses"], 3)
        self.assertTrue(merged["behavior_reset_required"])

    def test_merge_lets_explicit_keys_make_state_stricter(self) -> None:
        # The conservative merge still allows a caller to tighten the gate.
        save_trading_state(
            TradingStateRecord(drawdown_pct=-1.0, consecutive_losses=1),
            self.path,
        )
        merged = merge_into_risk_context(
            {
                "drawdown_pct": -9.0,
                "consecutive_losses": 5,
                "behavior_reset_required": True,
            },
            path=self.path,
        )
        self.assertEqual(merged["drawdown_pct"], -9.0)
        self.assertEqual(merged["consecutive_losses"], 5)
        self.assertTrue(merged["behavior_reset_required"])

    def test_persisted_hard_stop_state_blocks_next_risk_gate_run(self) -> None:
        from finharness.risk_gate import RiskGateContext

        save_trading_state(
            TradingStateRecord(drawdown_pct=-5.0, consecutive_losses=4),
            self.path,
        )
        merged = merge_into_risk_context(None, path=self.path)
        context = RiskGateContext.model_validate(merged)
        self.assertLessEqual(context.drawdown_pct, context.hard_stop_drawdown_pct)
        self.assertGreaterEqual(
            context.consecutive_losses, context.hard_stop_consecutive_losses
        )

    def test_saved_file_is_valid_json_with_schema_version(self) -> None:
        save_trading_state(TradingStateRecord(), self.path)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "finharness.trading_state.v1")


if __name__ == "__main__":
    unittest.main()
