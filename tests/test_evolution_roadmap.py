"""Compatibility entrypoint for the retired Markdown roadmap contract."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class EvolutionRoadmapRetirementTest(unittest.TestCase):
    def test_markdown_roadmap_is_historical_and_not_a_work_authority(self) -> None:
        roadmap = (
            ROOT / "docs" / "architecture" / "finharness-evolution-roadmap.md"
        ).read_text(encoding="utf-8")
        catalog = yaml.safe_load(
            (ROOT / "docs" / "architecture" / "system-catalog.yml").read_text(
                encoding="utf-8"
            )
        )

        self.assertIn("**Documentation lifecycle:** `historical`", roadmap)
        self.assertIn("Do not restore a maintained Markdown implementation sequence", roadmap)
        self.assertNotIn("implementation_sequence", catalog["fact_ownership"])
        self.assertNotIn(
            "evolution_roadmap",
            {system["id"] for system in catalog["systems"]},
        )
        self.assertEqual(
            catalog["fact_ownership"]["current_work_authorization"],
            "https://github.com/zycxfyh/FinHarness/issues",
        )


if __name__ == "__main__":
    unittest.main()
