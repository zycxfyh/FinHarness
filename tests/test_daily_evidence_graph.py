from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness import daily_evidence
from finharness.daily_evidence_graph import daily_evidence_graph, run_daily_evidence_graph


def market_result(symbol: str, *, quality_ok: bool = True) -> dict[str, object]:
    records = [
        {
            "date": "2026-01-02",
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 1000,
        },
        {
            "date": "2026-01-03",
            "open": 101.0,
            "high": 103.0,
            "low": 100.0,
            "close": 102.0,
            "volume": 1200,
        },
    ]
    return {
        "final": {
            "workflow": "langgraph_market_data_v1",
            "symbol": symbol,
            "quality_ok": quality_ok,
            "payload_ref": f"data/normalized/market-data/{symbol}.json",
            "receipt_ref": f"data/receipts/market-data/{symbol}.json",
            "execution_allowed": False,
        },
        "normalized_records": records,
        "snapshot": {
            "snapshot_id": f"mds_{symbol}",
            "payload_ref": f"data/normalized/market-data/{symbol}.json",
            "receipt_ref": f"data/receipts/market-data/{symbol}.json",
            "quality": {"ok": quality_ok},
        },
    }


def indicator_result(symbol: str, *, quality_ok: bool = True) -> dict[str, object]:
    return {
        "final": {
            "workflow": "langgraph_indicators_v1",
            "symbol": symbol,
            "quality_ok": quality_ok,
            "payload_ref": f"data/normalized/indicators/{symbol}.json",
            "receipt_ref": f"data/receipts/indicators/{symbol}.json",
            "execution_allowed": False,
        },
        "snapshot": {
            "indicator_snapshot_id": f"inds_{symbol}",
            "payload_ref": f"data/normalized/indicators/{symbol}.json",
            "receipt_ref": f"data/receipts/indicators/{symbol}.json",
            "quality": {"ok": quality_ok},
        },
    }


def events_result(*, quality_ok: bool = True, event_count: int = 3) -> dict[str, object]:
    return {
        "final": {
            "workflow": "langgraph_events_sec_edgar_v1",
            "quality_ok": quality_ok,
            "event_count": event_count,
            "payload_ref": "data/normalized/events/sec-edgar/evs.json",
            "receipt_ref": "data/receipts/events/evs.json",
            "execution_allowed": False,
        },
        "snapshot": {
            "snapshot_id": "evs_test",
            "event_count": event_count,
            "payload_ref": "data/normalized/events/sec-edgar/evs.json",
            "receipt_ref": "data/receipts/events/evs.json",
            "quality": {"ok": quality_ok},
        },
    }


def interpretation_result(*, quality_ok: bool = True) -> dict[str, object]:
    return {
        "final": {
            "workflow": "langgraph_interpretation_v1",
            "quality_ok": quality_ok,
            "payload_ref": "data/normalized/interpretations/ints.json",
            "receipt_ref": "data/receipts/interpretations/ints.json",
            "execution_allowed": False,
        },
        "snapshot": {
            "interpretation_snapshot_id": "ints_test",
            "payload_ref": "data/normalized/interpretations/ints.json",
            "receipt_ref": "data/receipts/interpretations/ints.json",
            "quality": {"ok": quality_ok},
        },
    }


class DailyEvidenceGraphTest(unittest.TestCase):
    def test_graph_compiles(self) -> None:
        self.assertIsNotNone(daily_evidence_graph)

    def test_success_path_links_refs_and_reuses_market_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            captured: dict[str, object] = {}

            def fake_indicator_graph(**kwargs):
                self.assertIn("market_data_snapshot", kwargs)
                self.assertIn("history_records", kwargs)
                return indicator_result(kwargs["symbol"])

            def fake_events_graph(**kwargs):
                captured["event_market_refs"] = kwargs["linked_market_snapshot_refs"]
                captured["event_indicator_refs"] = kwargs["linked_indicator_snapshot_refs"]
                return events_result()

            def fake_interpretation_graph(**kwargs):
                captured["interpretation_market_refs"] = kwargs["market_snapshot_refs"]
                captured["interpretation_indicator_refs"] = kwargs["indicator_snapshot_refs"]
                self.assertEqual(kwargs["event_snapshot"]["snapshot_id"], "evs_test")
                return interpretation_result()

            with (
                patch.object(
                    daily_evidence,
                    "DAILY_EVIDENCE_NORMALIZED_ROOT",
                    root / "normalized",
                ),
                patch.object(
                    daily_evidence,
                    "DAILY_EVIDENCE_RECEIPT_ROOT",
                    root / "receipts",
                ),
                patch.object(
                    daily_evidence,
                    "DAILY_EVIDENCE_REVIEW_ROOT",
                    root / "reviews",
                ),
                patch(
                    "finharness.daily_evidence_graph.run_market_data_graph",
                    side_effect=lambda **kwargs: market_result(kwargs["symbol"]),
                ),
                patch(
                    "finharness.daily_evidence_graph.run_indicator_graph",
                    side_effect=fake_indicator_graph,
                ),
                patch(
                    "finharness.daily_evidence_graph.run_events_graph",
                    side_effect=fake_events_graph,
                ),
                patch(
                    "finharness.daily_evidence_graph.run_interpretation_graph",
                    side_effect=fake_interpretation_graph,
                ),
            ):
                result = run_daily_evidence_graph(
                    universe=["AAPL", "SPY", "QQQ"],
                    market_symbols=["SPY", "QQQ"],
                    start="2026-01-01",
                    end="2026-01-05",
                    max_records=3,
                )
                receipt_exists = Path(result["final"]["receipt_ref"]).exists()
                review_exists = Path(result["final"]["review_hook"]["review_ref"]).exists()

        final = result["final"]
        self.assertEqual(final["workflow"], "langgraph_daily_evidence_v1")
        self.assertEqual(final["status"], "ok")
        self.assertTrue(final["quality_ok"])
        self.assertFalse(final["execution_allowed"])
        self.assertEqual(
            captured["event_market_refs"],
            [
                "data/normalized/market-data/SPY.json",
                "data/normalized/market-data/QQQ.json",
            ],
        )
        self.assertEqual(
            captured["event_indicator_refs"],
            [
                "data/normalized/indicators/SPY.json",
                "data/normalized/indicators/QQQ.json",
            ],
        )
        self.assertEqual(captured["interpretation_market_refs"], captured["event_market_refs"])
        self.assertEqual(
            captured["interpretation_indicator_refs"],
            captured["event_indicator_refs"],
        )
        self.assertTrue(receipt_exists)
        self.assertTrue(review_exists)

    def test_failed_market_quality_gate_stops_downstream_layers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(
                    daily_evidence,
                    "DAILY_EVIDENCE_NORMALIZED_ROOT",
                    root / "normalized",
                ),
                patch.object(
                    daily_evidence,
                    "DAILY_EVIDENCE_RECEIPT_ROOT",
                    root / "receipts",
                ),
                patch.object(
                    daily_evidence,
                    "DAILY_EVIDENCE_REVIEW_ROOT",
                    root / "reviews",
                ),
                patch(
                    "finharness.daily_evidence_graph.run_market_data_graph",
                    return_value=market_result("SPY", quality_ok=False),
                ),
                patch("finharness.daily_evidence_graph.run_indicator_graph") as indicators,
                patch("finharness.daily_evidence_graph.run_events_graph") as events,
                patch("finharness.daily_evidence_graph.run_interpretation_graph") as interp,
            ):
                result = run_daily_evidence_graph(
                    universe=["AAPL", "SPY"],
                    market_symbols=["SPY"],
                )
                receipt_exists = Path(result["final"]["receipt_ref"]).exists()
                review_exists = Path(result["final"]["review_hook"]["review_ref"]).exists()

        final = result["final"]
        self.assertEqual(final["status"], "failed")
        self.assertFalse(final["quality_ok"])
        self.assertEqual(final["failed_layers"], ["market_data"])
        indicators.assert_not_called()
        events.assert_not_called()
        interp.assert_not_called()
        self.assertTrue(receipt_exists)
        self.assertTrue(review_exists)

    def test_no_events_route_warns_and_skips_interpretation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(
                    daily_evidence,
                    "DAILY_EVIDENCE_NORMALIZED_ROOT",
                    root / "normalized",
                ),
                patch.object(
                    daily_evidence,
                    "DAILY_EVIDENCE_RECEIPT_ROOT",
                    root / "receipts",
                ),
                patch.object(
                    daily_evidence,
                    "DAILY_EVIDENCE_REVIEW_ROOT",
                    root / "reviews",
                ),
                patch(
                    "finharness.daily_evidence_graph.run_market_data_graph",
                    return_value=market_result("SPY"),
                ),
                patch(
                    "finharness.daily_evidence_graph.run_indicator_graph",
                    return_value=indicator_result("SPY"),
                ),
                patch(
                    "finharness.daily_evidence_graph.run_events_graph",
                    return_value=events_result(event_count=0),
                ),
                patch("finharness.daily_evidence_graph.run_interpretation_graph") as interp,
            ):
                result = run_daily_evidence_graph(
                    universe=["AAPL", "SPY"],
                    market_symbols=["SPY"],
                )
                receipt_exists = Path(result["final"]["receipt_ref"]).exists()
                review_exists = Path(result["final"]["review_hook"]["review_ref"]).exists()

        final = result["final"]
        self.assertEqual(final["status"], "warning")
        self.assertTrue(final["quality_ok"])
        self.assertEqual(final["failed_layers"], [])
        self.assertIsNone(final["interpretation_snapshot_ref"])
        interp.assert_not_called()
        self.assertTrue(receipt_exists)
        self.assertTrue(review_exists)


if __name__ == "__main__":
    unittest.main()
