from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness.market_cockpit import (
    build_market_cockpit,
    write_market_cockpit_outputs,
)


def fake_market_data(symbol: str, **_: object) -> dict[str, object]:
    records = [
        {
            "date": "2026-06-11 00:00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000,
        },
        {
            "date": "2026-06-12 00:00:00",
            "open": 102.0,
            "high": 103.0,
            "low": 101.0,
            "close": 102.0,
            "volume": 1200,
        },
    ]
    return {
        "normalized_records": records,
        "snapshot": {
            "snapshot_id": f"mds_{symbol}",
            "symbols": [symbol],
            "quality": {"ok": True, "row_count": 2, "notes": []},
            "payload_ref": f"data/normalized/market-data/{symbol}.json",
            "receipt_ref": f"data/receipts/market-data/{symbol}.json",
        },
        "final": {
            "symbol": symbol,
            "row_count": 2,
            "quality_ok": True,
            "quality_notes": ["nautilus catalog write skipped: overlap"],
            "payload_ref": f"data/normalized/market-data/{symbol}.json",
            "receipt_ref": f"data/receipts/market-data/{symbol}.json",
        },
    }


def fake_indicator(symbol: str, **_: object) -> dict[str, object]:
    return {
        "features": {
            "latest": {
                "ma_trend": "bullish",
                "rsi": 52.0,
                "rsi_state": "neutral",
                "macd_bias": "bearish",
                "macd_hist": -0.5,
                "rolling_volatility_20d_annualized": 0.15,
            }
        },
        "final": {
            "symbol": symbol,
            "quality_ok": True,
            "payload_ref": f"data/normalized/indicators/{symbol}.json",
            "receipt_ref": f"data/receipts/indicators/{symbol}.json",
        },
    }


class MarketCockpitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        (self.root / "data" / "normalized" / "hypotheses").mkdir(parents=True)
        (self.root / "data" / "normalized" / "validations").mkdir(parents=True)
        (self.root / "docs" / "reviews").mkdir(parents=True)
        (self.root / "data" / "normalized" / "hypotheses" / "hyps_latest.json").write_text(
            json.dumps(
                {
                    "hypothesis_snapshot_id": "hyps_latest",
                    "universe": ["SPY", "QQQ"],
                    "records": [],
                }
            ),
            encoding="utf-8",
        )
        (self.root / "data" / "normalized" / "validations" / "vals_latest.json").write_text(
            json.dumps(
                {
                    "validation_snapshot_id": "vals_latest",
                    "universe": ["SPY", "QQQ"],
                    "jobs": [],
                    "results": [],
                }
            ),
            encoding="utf-8",
        )
        (self.root / "docs" / "reviews" / "warning.md").write_text(
            "# Review\n\nStatus: warning\n\n```text\nreview_only\n```\n",
            encoding="utf-8",
        )

    def test_cockpit_aggregates_watchlist_visibility_without_execution(self) -> None:
        with (
            patch("finharness.market_cockpit.run_market_data_graph", side_effect=fake_market_data),
            patch("finharness.market_cockpit.run_indicator_graph", side_effect=fake_indicator),
            patch(
                "finharness.market_cockpit.build_receipt_usage_audit",
                return_value={
                    "summary": {
                        "receipt_count": 3,
                        "missing_reference_count": 1,
                        "evidence_surface_counts": {
                            "durable_consumed": 1,
                            "candidate_or_draft": 1,
                            "generated_runtime_or_unlinked": 1,
                        },
                    }
                },
            ),
        ):
            cockpit = build_market_cockpit(symbols="SPY,QQQ", root=self.root)

        self.assertFalse(cockpit["execution_allowed"])
        self.assertEqual([row["symbol"] for row in cockpit["symbols"]], ["SPY", "QQQ"])
        first = cockpit["symbols"][0]
        self.assertEqual(first["market_data"]["row_count"], 2)
        self.assertEqual(first["indicators"]["ma_trend"], "bullish")
        self.assertEqual(first["hypothesis"]["status"], "zero_records")
        self.assertEqual(first["validation"]["status"], "zero_results")
        self.assertIn("review_only_build_hypothesis", first["next_action"])
        self.assertTrue(cockpit["review_queue"])
        self.assertTrue(cockpit["degraded_paths"])
        issues = {item["issue"] for item in cockpit["broken_paths"]}
        self.assertIn("receipt_missing_references:1", issues)

    def test_cockpit_writes_json_and_markdown(self) -> None:
        cockpit = {
            "generated_at": "2026-06-14T00:00:00Z",
            "execution_allowed": False,
            "symbols": [
                {
                    "symbol": "SPY",
                    "market_data": {"latest_date": "2026-06-12", "freshness": {"status": "fresh"}},
                    "risk_return": {"ok": True, "total_return": 0.1, "max_drawdown": -0.05},
                    "indicators": {
                        "ma_trend": "bullish",
                        "rsi": 50,
                        "rsi_state": "neutral",
                        "macd_bias": "bearish",
                    },
                    "validation": {"status": "zero_results"},
                    "next_action": "review_only_build_hypothesis",
                }
            ],
            "broken_paths": [],
            "degraded_paths": [],
            "review_queue": [],
            "receipt_surface": {
                "summary": {
                    "receipt_count": 3,
                    "missing_reference_count": 0,
                    "evidence_surface_counts": {
                        "durable_consumed": 1,
                        "candidate_or_draft": 1,
                        "generated_runtime_or_unlinked": 1,
                    },
                }
            },
        }

        outputs = write_market_cockpit_outputs(cockpit, root=self.root)

        self.assertTrue(Path(outputs["receipt"]).exists())
        report = Path(outputs["report"]).read_text(encoding="utf-8")
        self.assertIn("Market Cockpit", report)
        self.assertIn("SPY", report)
        self.assertIn("Execution allowed: `false`", report)


if __name__ == "__main__":
    unittest.main()
