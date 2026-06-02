from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from finharness.indicator_graph import indicator_graph, run_indicator_graph
from finharness.market_data import SourceSpec, build_ohlcv_snapshot_from_history


def sample_history(rows: int = 90) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": f"2026-01-{index % 28 + 1:02d}",
                "open": 100.0 + index * 0.2,
                "high": 101.0 + index * 0.2,
                "low": 99.0 + index * 0.2,
                "close": 100.5 + index * 0.2,
                "volume": 1_000_000 + index,
            }
            for index in range(rows)
        ]
    )


def sample_market_data_graph_result() -> dict[str, object]:
    history = sample_history()
    receipt = build_ohlcv_snapshot_from_history(
        history,
        symbol="SPY",
        source=SourceSpec(
            provider="yfinance",
            upstream_source="Yahoo Finance",
            asset_class="equity",
            dataset="ohlcv_history",
            access_method="api_pull",
            wheel="yfinance",
            wheel_version="test",
        ),
        fetch_config={"symbol": "SPY"},
        raw_payload={"rows": len(history)},
        adjusted=False,
        write_catalog=False,
    )
    return {
        "final": {"workflow": "langgraph_market_data_v1", "symbol": "SPY"},
        "normalized_records": history.to_dict(orient="records"),
        "snapshot": receipt.snapshot.model_dump(mode="json"),
    }


class IndicatorGraphTest(unittest.TestCase):
    def test_graph_compiles(self) -> None:
        self.assertIsNotNone(indicator_graph)

    def test_graph_runs_strict_layer_flow(self) -> None:
        with patch(
            "finharness.indicator_graph.run_market_data_graph",
            return_value=sample_market_data_graph_result(),
        ):
            result = run_indicator_graph(
                symbol="SPY",
                start="2026-01-01",
                end="2026-04-01",
            )

        final = result["final"]
        self.assertEqual(final["workflow"], "langgraph_indicators_v1")
        self.assertEqual(final["symbol"], "SPY")
        self.assertTrue(final["quality_ok"])
        self.assertFalse(final["execution_allowed"])
        self.assertTrue(final["input_market_data_snapshot_id"])
        self.assertEqual(
            final["consumer_handoff"]["consumer"],
            "events_interpretation_research_review",
        )
        self.assertEqual(final["review_hook"]["status"], "open")

    def test_graph_can_reuse_existing_market_data_snapshot(self) -> None:
        market_data = sample_market_data_graph_result()
        with patch("finharness.indicator_graph.run_market_data_graph") as fetch_market_data:
            result = run_indicator_graph(
                symbol="SPY",
                start="2026-01-01",
                end="2026-04-01",
                ma_fast=5,
                ma_slow=20,
                market_data_snapshot=market_data["snapshot"],
                history_records=market_data["normalized_records"],
            )

        fetch_market_data.assert_not_called()
        final = result["final"]
        self.assertTrue(final["quality_ok"])
        specs = result["snapshot"]["lineage"]["indicator_specs"]
        fast_spec = next(spec for spec in specs if spec["name"] == "TA-Lib.SMA.fast")
        slow_spec = next(spec for spec in specs if spec["name"] == "TA-Lib.SMA.slow")
        self.assertEqual(fast_spec["params"]["window"], 5)
        self.assertEqual(slow_spec["params"]["window"], 20)


if __name__ == "__main__":
    unittest.main()
