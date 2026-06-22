"""Tests for the fail-closed live-order gate (red-team F1/F3/F4/F5/F7)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from finharness.lesson_loop import LessonDraft
from finharness.market_access_ledger import (
    MarketAccessLedgerError,
    MarketAccessLimit,
    record_consumption,
)
from finharness.okx_cli import OkxCliError, OkxCliResult
from finharness.okx_live_gate import (
    DEFAULT_LIVE_MARKET_ACCESS_LIMIT,
    LiveOrderBlocked,
    LiveOrderRequest,
    assess_live_order,
    execute_live_order,
    market_access_key_for_live_order,
    order_notional,
)
from finharness.rule_change_ledger import promote_lesson_to_rule_change
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
        "request_limit": 50.0,
    }
    base.update(overrides)
    return LiveOrderRequest(**base)


def _draft() -> LessonDraft:
    return LessonDraft(
        draft_id="lesson_draft_okx_ceiling",
        created_at_utc="2026-06-18T00:00:00+00:00",
        window_days=14,
        receipts_scanned=2,
        sources=["data/receipts/okx-live"],
        status_counts={"ok": 2},
        quality_failure_count=0,
        top_blocking_reasons=[],
        observations=["operator reviewed OKX ceiling"],
        proposed_rule_changes=[],
        receipt_refs=["receipt_okx_a", "receipt_okx_b"],
    )


def _promote_ceiling(rule_state: Path, receipt_root: Path, *, target: str, value: float):
    return promote_lesson_to_rule_change(
        lesson_draft=_draft(),
        rule_target=target,
        change_kind="threshold",
        old_value=50.0,
        new_value=value,
        rationale="human reviewed ceiling change with receipt lineage",
        attester="operator",
        lesson_doc_ref="docs/lessons/2026-06-18-okx-ceiling.md",
        state_root=rule_state,
        receipt_root=receipt_root,
    )


class OkxLiveGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trading-state.json"
        self.root = Path(self.tmp.name)
        self.env_patch = mock.patch.dict(
            os.environ,
            {
                "FINHARNESS_MARKET_ACCESS_LEDGER_PATH": str(self.root / "ledger.json"),
                "FINHARNESS_MARKET_ACCESS_RECEIPT_ROOT": str(self.root / "receipts"),
            },
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
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
        self.assertTrue(any("exceeds enforced cap" in r for r in decision.blocking_reasons))

    def test_request_limit_cannot_raise_live_ceiling_without_lineage(self) -> None:
        req = _request(
            args=["--instId", "BTC-USDT-SWAP", "--sz", "0.6", "--px", "100"],
            request_limit=10_000.0,
        )

        decision = assess_live_order(
            req,
            state_path=self.path,
            market_access_limit=MarketAccessLimit(
                max_window_notional=10_000.0,
                max_window_order_count=10,
            ),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.enforced_cap, 50.0)
        self.assertEqual(decision.effective_ceiling, 50.0)
        self.assertTrue(decision.request_limit_clamped_to_ceiling)
        self.assertTrue(decision.cap_invariant_holds)
        self.assertIsNone(decision.ceiling_provenance)
        self.assertTrue(any("exceeds enforced cap" in r for r in decision.blocking_reasons))

    def test_traceable_rule_change_can_raise_live_and_market_access_ceiling(
        self,
    ) -> None:
        rule_state = self.root / "rule-changes"
        rule_receipts = self.root / "rule-receipts"
        single_cap = _promote_ceiling(
            rule_state,
            rule_receipts,
            target="ceiling.max_live_notional",
            value=100.0,
        )
        aggregate_cap = _promote_ceiling(
            rule_state,
            rule_receipts,
            target="ceiling.live_market_access_window_notional",
            value=100.0,
        )
        req = _request(
            args=["--instId", "BTC-USDT-SWAP", "--sz", "0.6", "--px", "100"],
            request_limit=10_000.0,
        )

        decision = assess_live_order(
            req,
            state_path=self.path,
            ceiling_rule_root=rule_state,
            market_access_limit=MarketAccessLimit(
                max_window_notional=10_000.0,
                max_window_order_count=10,
            ),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.enforced_cap, 100.0)
        self.assertTrue(decision.request_limit_clamped_to_ceiling)
        self.assertIsNotNone(decision.ceiling_provenance)
        self.assertEqual(decision.ceiling_provenance["source_id"], single_cap.rule_change_id)
        self.assertIsNotNone(decision.market_access)
        self.assertEqual(decision.market_access.enforced_cap, 100.0)
        self.assertEqual(
            decision.market_access.ceiling_provenance["source_id"],
            aggregate_cap.rule_change_id,
        )

    def test_over_aggregate_notional_blocks_even_when_order_cap_passes(self) -> None:
        req = _request(args=["--instId", "BTC-USDT-SWAP", "--sz", "0.01", "--px", "100"])
        record_consumption(
            key=market_access_key_for_live_order(req),
            notional=50.0,
            limit=DEFAULT_LIVE_MARKET_ACCESS_LIMIT,
        )

        decision = assess_live_order(req, state_path=self.path)

        self.assertFalse(decision.allowed)
        self.assertTrue(
            any("market-access ledger" in reason for reason in decision.blocking_reasons)
        )

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
        receipts = list(receipt_root.glob("okxlive_*.json"))
        self.assertEqual(len(receipts), 1)
        payload = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["outcome"], "blocked")
        self.assertEqual(payload["request"]["request_limit"], 50.0)
        self.assertEqual(payload["decision"]["enforced_cap"], 50.0)
        self.assertTrue(payload["decision"]["cap_invariant_holds"])
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
        # Scope to the live-order receipt prefix: when record_consumption succeeds it
        # writes a co-located market-access receipt (receipt_mktacc_*) into the same dir
        # (setUp points FINHARNESS_MARKET_ACCESS_RECEIPT_ROOT at it), so a bare "*.json"
        # glob non-deterministically picked the wrong file (CI red, local green).
        receipt = next(iter(receipt_root.glob("okxlive_*.json")))
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(payload["outcome"], "executed")
        # F5: the placed order updated persisted state
        self.assertEqual(load_trading_state(self.path).trades_recorded, 1)

    def test_market_access_record_failure_never_calls_okx(self) -> None:
        receipt_root = Path(self.tmp.name) / "receipts"
        with mock.patch("finharness.okx_live_gate.LIVE_ORDER_RECEIPT_ROOT", receipt_root), \
             mock.patch(
                 "finharness.okx_live_gate.record_consumption",
                 side_effect=MarketAccessLedgerError("disk full"),
             ), mock.patch(
                 "finharness.okx_live_gate.run_okx_live_mutation_command",
             ) as run, self.assertRaises(OkxCliError):
            execute_live_order(_request(), state_path=self.path)

        run.assert_not_called()
        receipt = next(iter(receipt_root.glob("okxlive_*.json")))
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(payload["outcome"], "error")
        self.assertIn("before OKX submit", payload["error"])
        self.assertEqual(load_trading_state(self.path).trades_recorded, 0)

    def test_okx_error_writes_error_receipt_and_no_state_update(self) -> None:
        receipt_root = Path(self.tmp.name) / "receipts"
        with mock.patch("finharness.okx_live_gate.LIVE_ORDER_RECEIPT_ROOT", receipt_root), \
             mock.patch(
                 "finharness.okx_live_gate.run_okx_live_mutation_command",
                 side_effect=OkxCliError("boom"),
             ), self.assertRaises(OkxCliError):
            execute_live_order(_request(), state_path=self.path)
        receipt = next(iter(receipt_root.glob("okxlive_*.json")))
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        self.assertEqual(payload["outcome"], "error")
        self.assertEqual(load_trading_state(self.path).trades_recorded, 0)


if __name__ == "__main__":
    unittest.main()
