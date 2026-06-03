from __future__ import annotations

import unittest
from unittest.mock import patch

from finharness.ten_layer_graph import run_ten_layer_graph, ten_layer_graph


def layer_result(layer: int, key: str) -> dict[str, dict[str, object]]:
    snapshot = {
        f"{key}_snapshot_id": f"{key}_snapshot",
        "payload_ref": f"data/normalized/{key}.json",
        "receipt_ref": f"data/receipts/{key}.json",
    }
    if key == "execution":
        snapshot |= {"final_status": "filled", "execution_allowed": False}
    if key == "post_trade":
        snapshot |= {"final_status": "reconciled_filled", "order_creation_allowed": False}
    return {
        "snapshot": snapshot,
        "final": {
            "workflow": f"mock_{key}_graph",
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
        },
    }


class TenLayerGraphTest(unittest.TestCase):
    def test_ten_layer_graph_compiles(self) -> None:
        self.assertIsNotNone(ten_layer_graph)

    def test_full_chain_calls_each_layer_once(self) -> None:
        calls: list[str] = []

        def fake(name: str, layer: int):
            def _call(**kwargs):
                calls.append(name)
                return layer_result(layer, name)

            return _call

        with (
            patch("finharness.ten_layer_graph.run_market_data_graph", fake("market_data", 1)),
            patch("finharness.ten_layer_graph.run_indicator_graph", fake("indicators", 2)),
            patch("finharness.ten_layer_graph.run_events_graph", fake("events", 3)),
            patch(
                "finharness.ten_layer_graph.run_interpretation_graph",
                fake("interpretation", 4),
            ),
            patch("finharness.ten_layer_graph.run_hypotheses_graph", fake("hypotheses", 5)),
            patch("finharness.ten_layer_graph.run_validation_graph", fake("validation", 6)),
            patch("finharness.ten_layer_graph.run_proposal_graph", fake("proposal", 7)),
            patch("finharness.ten_layer_graph.run_risk_gate_graph", fake("risk_gate", 8)),
            patch("finharness.ten_layer_graph.run_execution_graph", fake("execution", 9)),
            patch("finharness.ten_layer_graph.run_post_trade_graph", fake("post_trade", 10)),
        ):
            result = run_ten_layer_graph(run_layers=list(range(1, 11)))

        self.assertEqual(
            calls,
            [
                "market_data",
                "indicators",
                "events",
                "interpretation",
                "hypotheses",
                "validation",
                "proposal",
                "risk_gate",
                "execution",
                "post_trade",
            ],
        )
        final = result["final"]
        self.assertEqual(final["workflow"], "langgraph_ten_layer_orchestrator_v1")
        self.assertEqual(final["terminal_layer"], "post_trade")
        self.assertEqual(final["terminal_status"], "reconciled_filled")
        self.assertFalse(final["order_creation_allowed"])
        self.assertTrue(
            all(item["status"] == "ran" for item in final["layer_status"].values())
        )

    def test_can_reuse_execution_snapshot_and_run_only_post_trade(self) -> None:
        execution_snapshot = {
            "execution_snapshot_id": "exsnap_reused",
            "payload_ref": "data/normalized/execution.json",
            "receipt_ref": "data/receipts/execution.json",
            "final_status": "filled",
            "execution_allowed": False,
        }
        with patch(
            "finharness.ten_layer_graph.run_post_trade_graph",
            return_value=layer_result(10, "post_trade"),
        ) as post_trade_call:
            result = run_ten_layer_graph(
                run_layers=[10],
                snapshots={"execution_snapshot": execution_snapshot},
            )

        final = result["final"]
        self.assertEqual(post_trade_call.call_count, 1)
        self.assertEqual(final["layer_status"]["execution"]["status"], "reused")
        self.assertEqual(final["layer_status"]["post_trade"]["status"], "ran")
        self.assertEqual(final["layer_status"]["market_data"]["status"], "skipped")
        self.assertEqual(final["terminal_layer"], "post_trade")

    def test_research_asset_ids_are_passed_to_l5_l10_and_reported(self) -> None:
        captured: dict[str, dict[str, object]] = {}

        def fake(name: str, layer: int):
            def _call(**kwargs):
                if layer >= 5:
                    captured[name] = kwargs["research_asset_context"]
                return layer_result(layer, name)

            return _call

        with (
            patch("finharness.ten_layer_graph.run_market_data_graph", fake("market_data", 1)),
            patch("finharness.ten_layer_graph.run_indicator_graph", fake("indicators", 2)),
            patch("finharness.ten_layer_graph.run_events_graph", fake("events", 3)),
            patch(
                "finharness.ten_layer_graph.run_interpretation_graph",
                fake("interpretation", 4),
            ),
            patch("finharness.ten_layer_graph.run_hypotheses_graph", fake("hypotheses", 5)),
            patch("finharness.ten_layer_graph.run_validation_graph", fake("validation", 6)),
            patch("finharness.ten_layer_graph.run_proposal_graph", fake("proposal", 7)),
            patch("finharness.ten_layer_graph.run_risk_gate_graph", fake("risk_gate", 8)),
            patch("finharness.ten_layer_graph.run_execution_graph", fake("execution", 9)),
            patch("finharness.ten_layer_graph.run_post_trade_graph", fake("post_trade", 10)),
        ):
            result = run_ten_layer_graph(
                run_layers=list(range(1, 11)),
                research_asset_ids=[
                    "strategy.trend_following.v0",
                    "math.validation.walk_forward.v0",
                    "reference.tool.vectorbt.v0",
                    "missing.asset.v0",
                ],
            )

        self.assertEqual(
            set(captured),
            {"hypotheses", "validation", "proposal", "risk_gate", "execution", "post_trade"},
        )
        for context in captured.values():
            self.assertFalse(context["execution_allowed"])
            self.assertEqual(context["missing_ids"], ["missing.asset.v0"])

        refs = result["final"]["research_asset_refs"]
        self.assertEqual(refs["strategy_ids"], ["strategy.trend_following.v0"])
        self.assertEqual(refs["method_ids"], ["math.validation.walk_forward.v0"])
        self.assertEqual(refs["reference_ids"], ["reference.tool.vectorbt.v0"])
        self.assertEqual(refs["missing_ids"], ["missing.asset.v0"])
        self.assertFalse(refs["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
