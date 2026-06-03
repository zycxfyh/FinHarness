from __future__ import annotations

import unittest

from finharness import (
    execution_graph,
    hypotheses_graph,
    post_trade_graph,
    proposal_graph,
    risk_gate_graph,
    validation_graph,
)
from finharness.research_assets import resolve_research_assets


class ResearchAssetHandoffTest(unittest.TestCase):
    def test_l5_l10_source_configs_record_layer_filtered_asset_refs(self) -> None:
        context = resolve_research_assets(
            research_asset_ids=[
                "strategy.trend_following.v0",
                "math.validation.walk_forward.v0",
                "reference.provider.alpaca_paper_adapter.v0",
                "missing.asset.v0",
            ]
        ).model_dump(mode="json")

        states = {
            "L5": hypotheses_graph.source_config_node(
                {"research_asset_context": context}
            )["source"]["config"]["research_asset_context"],
            "L6": validation_graph.source_config_node(
                {"research_asset_context": context}
            )["source"]["config"]["research_asset_context"],
            "L7": proposal_graph.source_config_node(
                {"research_asset_context": context}
            )["source"]["config"]["research_asset_context"],
            "L8": risk_gate_graph.source_config_node(
                {"research_asset_context": context}
            )["source"]["config"]["research_asset_context"],
            "L9": execution_graph.source_config_node(
                {"research_asset_context": context}
            )["source"]["config"]["research_asset_context"],
            "L10": post_trade_graph.source_config_node(
                {"research_asset_context": context}
            )["source"]["config"]["research_asset_context"],
        }

        for layer, asset_context in states.items():
            self.assertEqual(asset_context["layer"], layer)
            self.assertEqual(asset_context["missing_ids"], ["missing.asset.v0"])
            self.assertFalse(asset_context["execution_allowed"])

        self.assertIn("strategy.trend_following.v0", states["L5"]["strategy_ids"])
        self.assertIn("math.validation.walk_forward.v0", states["L6"]["method_ids"])
        self.assertIn("strategy.trend_following.v0", states["L8"]["strategy_ids"])
        self.assertIn(
            "reference.provider.alpaca_paper_adapter.v0",
            states["L9"]["reference_ids"],
        )
        self.assertIn(
            "reference.provider.alpaca_paper_adapter.v0",
            states["L10"]["reference_ids"],
        )


if __name__ == "__main__":
    unittest.main()
