from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from finharness.research_assets import (
    ReferenceCard,
    StrategySpec,
    compact_research_asset_context,
    load_research_asset_catalog,
    resolve_research_assets,
)


class ResearchAssetLibraryTest(unittest.TestCase):
    def test_sample_catalog_loads_expected_assets_without_execution_authority(self) -> None:
        catalog = load_research_asset_catalog()
        summary = catalog.summary()

        self.assertEqual(summary["strategy_spec_count"], 3)
        self.assertEqual(summary["method_spec_count"], 6)
        self.assertEqual(summary["reference_card_count"], 10)
        self.assertFalse(summary["execution_allowed"])
        self.assertIn("strategy.trend_following.v0", summary["strategy_ids"])
        self.assertIn("math.validation.walk_forward.v0", summary["method_ids"])
        self.assertIn("reference.tool.vectorbt.v0", summary["reference_ids"])

        for asset in [
            *catalog.strategy_specs,
            *catalog.method_specs,
            *catalog.reference_cards,
        ]:
            self.assertTrue(asset.no_execution_authority)

    def test_strategy_spec_requires_known_layer_refs(self) -> None:
        good = load_research_asset_catalog().strategy_specs[0].model_dump(mode="json")
        with self.assertRaises(ValidationError):
            StrategySpec.model_validate(good | {"used_by_layers": ["L11"]})

    def test_loader_accepts_custom_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "strategy-specs").mkdir(parents=True)
            (root / "method-specs").mkdir()
            (root / "reference-cards").mkdir()
            sample = load_research_asset_catalog().strategy_specs[0]
            (root / "strategy-specs" / "sample.json").write_text(
                sample.model_dump_json(indent=2),
                encoding="utf-8",
            )

            catalog = load_research_asset_catalog(root)
            self.assertEqual([item.id for item in catalog.strategy_specs], [sample.id])
            self.assertEqual(catalog.method_specs, [])
            self.assertEqual(catalog.reference_cards, [])

    def test_reference_card_blocks_unknown_integration_status(self) -> None:
        good = load_research_asset_catalog().reference_cards[0].model_dump(mode="json")
        with self.assertRaises(ValidationError):
            ReferenceCard.model_validate(good | {"integration_status": "live_write"})

    def test_resolve_research_assets_splits_ids_and_reports_missing(self) -> None:
        selection = resolve_research_assets(
            research_asset_ids=[
                "strategy.trend_following.v0",
                "math.validation.walk_forward.v0",
                "reference.tool.vectorbt.v0",
                "missing.asset.v0",
            ]
        )

        summary = selection.summary()
        self.assertEqual(summary["strategy_ids"], ["strategy.trend_following.v0"])
        self.assertEqual(summary["method_ids"], ["math.validation.walk_forward.v0"])
        self.assertEqual(summary["reference_ids"], ["reference.tool.vectorbt.v0"])
        self.assertEqual(summary["missing_ids"], ["missing.asset.v0"])
        self.assertFalse(summary["execution_allowed"])

    def test_compact_context_filters_by_layer_without_execution_authority(self) -> None:
        selection = resolve_research_assets(
            research_asset_ids=[
                "strategy.trend_following.v0",
                "math.validation.walk_forward.v0",
                "reference.provider.alpaca_paper_adapter.v0",
            ]
        )

        l6_context = compact_research_asset_context(
            selection.model_dump(mode="json"), "L6"
        )
        l9_context = compact_research_asset_context(
            selection.model_dump(mode="json"), "L9"
        )

        self.assertIn("strategy.trend_following.v0", l6_context["strategy_ids"])
        self.assertIn("math.validation.walk_forward.v0", l6_context["method_ids"])
        self.assertNotIn("reference.provider.alpaca_paper_adapter.v0", l6_context["reference_ids"])
        self.assertIn("reference.provider.alpaca_paper_adapter.v0", l9_context["reference_ids"])
        self.assertFalse(l6_context["execution_allowed"])
        self.assertFalse(l9_context["execution_allowed"])
