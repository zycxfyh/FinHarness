from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from finharness.daily_change_brief import run_daily_change_brief
from finharness.statecore.diff import diff_snapshots
from finharness.statecore.models import Position, Proposal, ReceiptIndex, Snapshot
from finharness.statecore.observations import (
    ObservationThresholds,
    build_observations,
)
from finharness.statecore.snapshot_ingest import ingest_portfolio_snapshot_from_receipt
from finharness.statecore.snapshots import latest_portfolio_snapshot, portfolio_positions
from finharness.statecore.store import init_state_core, read_all


class DailyChangeBriefTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.receipt_root = self.root / "receipts"
        self.markdown_path = self.root / "operations" / "daily-change-brief-latest.md"
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _write_portfolio_receipt(
        self,
        name: str,
        *,
        as_of_utc: str,
        positions: list[dict[str, object]],
    ) -> Path:
        path = self.root / "broker-read" / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        exact_positions = []
        for position in positions:
            exact = {
                key: (
                    str(value)
                    if key in {"qty", "quantity", "market_value", "cost_basis"}
                    else value
                )
                for key, value in position.items()
            }
            exact["currency"] = "USD"
            quantity = Decimal(str(position.get("qty", position.get("quantity"))))
            market_value = Decimal(str(position["market_value"]))
            exact.update(
                {
                    "unit_price": str(market_value / quantity),
                    "valuation_currency": "USD",
                    "price_currency": "USD",
                    "price_source_ref": f"fixture:{name}",
                }
            )
            exact_positions.append(exact)
        payload = {
            "receipt_id": f"receipt_{name}",
            "kind": "broker_read",
            "created_at_utc": as_of_utc,
            "effective_at_utc": as_of_utc,
            "observed_at_utc": as_of_utc,
            "valued_at_utc": as_of_utc,
            "broker": "manual",
            "environment": "paper",
            "account": {
                "id": "acct_daily",
                "status": "ACTIVE",
            },
            "positions": exact_positions,
            "execution_allowed": False,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def _thresholds(self) -> ObservationThresholds:
        return ObservationThresholds(
            min_position_market_value=25.0,
            quantity_change_pct=0.25,
            market_value_change_pct=0.25,
            total_exposure_change_pct=0.20,
            concentration_pct=0.70,
            data_gap_min_market_value=1.0,
        )

    def _run(self, receipt: Path, thresholds: ObservationThresholds | None = None):
        return run_daily_change_brief(
            portfolio_receipt=receipt,
            engine=self.engine,
            thresholds=thresholds or self._thresholds(),
            state_core_receipt_root=self.receipt_root / "state-core",
            brief_receipt_root=self.receipt_root / "daily-change-brief",
            markdown_path=self.markdown_path,
        )

    def test_latest_snapshot_finds_previous_and_first_run_is_baseline(self) -> None:
        day1 = self._write_portfolio_receipt(
            "day1",
            as_of_utc="2026-06-17T09:00:00+00:00",
            positions=[
                {"symbol": "SPY", "qty": 10, "market_value": 1000, "cost_basis": 900},
            ],
        )
        day2 = self._write_portfolio_receipt(
            "day2",
            as_of_utc="2026-06-18T09:00:00+00:00",
            positions=[
                {"symbol": "SPY", "qty": 11, "market_value": 1100, "cost_basis": 990},
            ],
        )

        first = ingest_portfolio_snapshot_from_receipt(day1, engine=self.engine)
        self.assertIsNone(latest_portfolio_snapshot(engine=self.engine, before=first.as_of_utc))

        second = ingest_portfolio_snapshot_from_receipt(day2, engine=self.engine)
        previous = latest_portfolio_snapshot(engine=self.engine, before=second.as_of_utc)
        self.assertIsNotNone(previous)
        self.assertEqual(previous.snapshot_id, first.snapshot_id)

        ingest_portfolio_snapshot_from_receipt(day2, engine=self.engine)
        self.assertEqual(len(read_all(Snapshot, engine=self.engine)), 2)
        self.assertEqual(len(read_all(Position, engine=self.engine)), 2)

    def test_observations_are_deterministic_facts_with_thresholds(self) -> None:
        before_path = self._write_portfolio_receipt(
            "before",
            as_of_utc="2026-06-17T09:00:00+00:00",
            positions=[
                {"symbol": "SPY", "qty": 10, "market_value": 1000, "cost_basis": 800},
                {"symbol": "QQQ", "qty": 5, "market_value": 500, "cost_basis": 450},
            ],
        )
        after_path = self._write_portfolio_receipt(
            "after",
            as_of_utc="2026-06-18T09:00:00+00:00",
            positions=[
                {"symbol": "SPY", "qty": 15, "market_value": 1600, "cost_basis": 1200},
                {"symbol": "AAPL", "qty": 2, "market_value": 400},
            ],
        )
        before = ingest_portfolio_snapshot_from_receipt(before_path, engine=self.engine)
        after = ingest_portfolio_snapshot_from_receipt(after_path, engine=self.engine)
        diff = diff_snapshots(before.snapshot_id, after.snapshot_id, engine=self.engine)

        observations = build_observations(
            diff,
            portfolio_positions(after.snapshot_id, engine=self.engine),
            thresholds=self._thresholds(),
        )

        self.assertEqual(
            [observation.kind for observation in observations],
            [
                "new_position",
                "closed_position",
                "material_move",
                "total_exposure_delta",
                "concentration",
                "data_gap",
            ],
        )
        banned_terms = ("should", "recommend", "forecast", "predict", "buy", "sell")
        details = " ".join(observation.detail.lower() for observation in observations)
        for term in banned_terms:
            self.assertNotIn(term, details)
        self.assertTrue(all(observation.crossed for observation in observations))
        self.assertEqual(observations[0].threshold["min_position_market_value"], 25.0)

    def test_no_threshold_crossing_returns_empty_observations(self) -> None:
        before_path = self._write_portfolio_receipt(
            "quiet-before",
            as_of_utc="2026-06-17T09:00:00+00:00",
            positions=[
                {"symbol": "SPY", "qty": 10, "market_value": 1000, "cost_basis": 900},
                {"symbol": "QQQ", "qty": 10, "market_value": 1000, "cost_basis": 900},
            ],
        )
        after_path = self._write_portfolio_receipt(
            "quiet-after",
            as_of_utc="2026-06-18T09:00:00+00:00",
            positions=[
                {"symbol": "SPY", "qty": 10.01, "market_value": 1005, "cost_basis": 900},
                {"symbol": "QQQ", "qty": 9.99, "market_value": 995, "cost_basis": 900},
            ],
        )
        before = ingest_portfolio_snapshot_from_receipt(before_path, engine=self.engine)
        after = ingest_portfolio_snapshot_from_receipt(after_path, engine=self.engine)
        diff = diff_snapshots(before.snapshot_id, after.snapshot_id, engine=self.engine)

        observations = build_observations(
            diff,
            portfolio_positions(after.snapshot_id, engine=self.engine),
            thresholds=ObservationThresholds(
                quantity_change_pct=0.99,
                market_value_change_pct=0.99,
                total_exposure_change_pct=0.99,
                concentration_pct=0.80,
            ),
        )

        self.assertEqual(observations, ())

    def test_daily_loop_writes_governed_proposal_markdown_and_rebuildable_receipt(self) -> None:
        day1 = self._write_portfolio_receipt(
            "loop-day1",
            as_of_utc="2026-06-17T09:00:00+00:00",
            positions=[
                {"symbol": "SPY", "qty": 10, "market_value": 1000, "cost_basis": 800},
                {"symbol": "QQQ", "qty": 5, "market_value": 500, "cost_basis": 450},
            ],
        )
        day2 = self._write_portfolio_receipt(
            "loop-day2",
            as_of_utc="2026-06-18T09:00:00+00:00",
            positions=[
                {"symbol": "SPY", "qty": 15, "market_value": 1600, "cost_basis": 1200},
                {"symbol": "AAPL", "qty": 2, "market_value": 400},
            ],
        )

        baseline = self._run(day1)
        self.assertEqual(baseline.status, "baseline")
        self.assertIsNone(baseline.before_snapshot_id)
        self.assertFalse(baseline.execution_allowed)

        result = self._run(day2)
        self.assertEqual(result.status, "observations")
        self.assertEqual(result.before_snapshot_id, baseline.after_snapshot_id)
        self.assertEqual(result.observation_count, 6)
        self.assertFalse(result.execution_allowed)

        markdown = self.markdown_path.read_text(encoding="utf-8")
        self.assertIn("Daily Change Brief", markdown)
        self.assertIn("Execution allowed: `false`", markdown)
        self.assertIn("Not a market prediction.", markdown)
        self.assertIn("`concentration`", markdown)

        proposals = read_all(Proposal, engine=self.engine)
        daily_proposal = next(
            proposal
            for proposal in proposals
            if proposal.proposal_id == result.proposal_id
        )
        self.assertEqual(daily_proposal.kind, "daily_change_brief")
        self.assertFalse(daily_proposal.execution_allowed)
        self.assertEqual(daily_proposal.evidence["status"], "observations")
        self.assertEqual(len(daily_proposal.evidence["observations"]), 6)
        self.assertFalse(daily_proposal.limitations["llm_used"])
        self.assertFalse(daily_proposal.limitations["broker_called_by_loop"])
        self.assertIn("Not trading advice.", daily_proposal.non_claims)

        brief_payload = json.loads(Path(result.receipt_ref).read_text(encoding="utf-8"))
        self.assertEqual(brief_payload["kind"], "daily_change_brief")
        self.assertEqual(brief_payload["proposal_id"], result.proposal_id)
        self.assertEqual(brief_payload["before_snapshot_id"], baseline.after_snapshot_id)
        self.assertFalse(brief_payload["execution_allowed"])
        self.assertEqual(len(brief_payload["observations"]), 6)
        self.assertIn(str(day2), brief_payload["source_refs"])

        proposal_count = len(read_all(Proposal, engine=self.engine))
        receipt_count = len(read_all(ReceiptIndex, engine=self.engine))
        snapshot_count = len(read_all(Snapshot, engine=self.engine))
        repeated = self._run(day2)
        self.assertEqual(repeated.proposal_id, result.proposal_id)
        self.assertEqual(repeated.receipt_ref, result.receipt_ref)
        self.assertEqual(len(read_all(Proposal, engine=self.engine)), proposal_count)
        self.assertEqual(len(read_all(ReceiptIndex, engine=self.engine)), receipt_count)
        self.assertEqual(len(read_all(Snapshot, engine=self.engine)), snapshot_count)

    def test_daily_loop_has_quiet_path_when_no_threshold_crosses(self) -> None:
        thresholds = ObservationThresholds(
            quantity_change_pct=0.99,
            market_value_change_pct=0.99,
            total_exposure_change_pct=0.99,
            concentration_pct=0.80,
        )
        day1 = self._write_portfolio_receipt(
            "quiet-loop-day1",
            as_of_utc="2026-06-17T09:00:00+00:00",
            positions=[
                {"symbol": "SPY", "qty": 10, "market_value": 1000, "cost_basis": 900},
                {"symbol": "QQQ", "qty": 10, "market_value": 1000, "cost_basis": 900},
            ],
        )
        day2 = self._write_portfolio_receipt(
            "quiet-loop-day2",
            as_of_utc="2026-06-18T09:00:00+00:00",
            positions=[
                {"symbol": "SPY", "qty": 10, "market_value": 1000, "cost_basis": 900},
                {"symbol": "QQQ", "qty": 10, "market_value": 1000, "cost_basis": 900},
            ],
        )

        self._run(day1, thresholds=thresholds)
        result = self._run(day2, thresholds=thresholds)

        self.assertEqual(result.status, "quiet")
        self.assertEqual(result.observation_count, 0)
        self.assertFalse(result.execution_allowed)
        markdown = self.markdown_path.read_text(encoding="utf-8")
        self.assertIn("No threshold-crossing portfolio state changes.", markdown)


if __name__ == "__main__":
    unittest.main()
