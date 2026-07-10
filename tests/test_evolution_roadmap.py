"""Current-fact checks for the maintained FinHarness evolution roadmap."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.test_agent_work_loop_acceptance import (
    EXPECTED_OPEN_CHECKS,
    EXPECTED_PASSING_CHECKS,
)

ROOT = Path(__file__).resolve().parents[1]
ROADMAP = ROOT / "docs" / "architecture" / "finharness-evolution-roadmap.md"
DEBT_REGISTER = ROOT / "docs" / "governance" / "debt-register.json"


def _roadmap() -> str:
    return ROADMAP.read_text(encoding="utf-8")


def _marked_section(text: str, marker: str) -> str:
    start = f"<!-- {marker}:start -->"
    end = f"<!-- {marker}:end -->"
    return text.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]


class EvolutionRoadmapCurrentFactsTest(unittest.TestCase):
    def test_roadmap_is_current_and_indexed(self) -> None:
        text = _roadmap()
        framework = (ROOT / "docs" / "architecture" / "framework-index.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Status: current", text)
        self.assertIn("Updated: 2026-07-10", text)
        self.assertIn("| Evolution Roadmap |", framework)
        self.assertIn("finharness-evolution-roadmap.md", framework)

    def test_active_debt_block_matches_canonical_register(self) -> None:
        register = json.loads(DEBT_REGISTER.read_text(encoding="utf-8"))
        active = {debt["id"] for debt in register["debts"] if debt["status"] == "active"}
        resolved = {debt["id"] for debt in register["debts"] if debt["status"] == "resolved"}
        section = _marked_section(_roadmap(), "active-debt")
        documented = set(re.findall(r"ENG-DEBT-\d{4}", section))

        self.assertEqual(documented, active)
        self.assertTrue(resolved.isdisjoint(documented))
        self.assertEqual(len(active), 1)
        self.assertEqual(len(resolved), 9)
        self.assertIn("9 resolved; 1 active", _roadmap())

    def test_agent_acceptance_block_matches_executable_baseline(self) -> None:
        section = _marked_section(_roadmap(), "agent-open")
        documented = set(re.findall(r"`([a-z0-9_]+)`", section))
        self.assertEqual(documented, EXPECTED_OPEN_CHECKS)
        self.assertEqual(len(EXPECTED_OPEN_CHECKS), 11)
        self.assertEqual(len(EXPECTED_PASSING_CHECKS), 4)
        for check_id in EXPECTED_PASSING_CHECKS:
            with self.subTest(passing_check=check_id):
                self.assertIn(f"`{check_id}`", _roadmap())

    def test_pr_genealogy_records_causal_phases(self) -> None:
        text = _roadmap()
        dash = "\N{EN DASH}"
        required_ranges = (
            f"#78{dash}#102",
            f"#103{dash}#113",
            f"#114{dash}#124",
            f"#125{dash}#152",
            f"#158{dash}#189",
            f"#190{dash}#217",
            f"#218{dash}#227",
        )
        for pr_range in required_ranges:
            with self.subTest(pr_range=pr_range):
                self.assertIn(pr_range, text)
        for commit in ("c7be442", "17ef59a", "3d6d1fa", "33fadd6", "fcb4d86"):
            with self.subTest(commit=commit):
                self.assertIn(f"`{commit}`", text)

    def test_responsibility_boundaries_are_explicit(self) -> None:
        text = _roadmap()
        required = (
            "Agentic Judgment Plane",
            "Classical Software Plane",
            "Human Authority Plane",
            "A model response never mutates StateCore by itself.",
            "Execution remains entirely classical.",
            "Human approval is not inferred from conversation or model confidence.",
        )
        for statement in required:
            with self.subTest(statement=statement):
                self.assertIn(statement, text)

    def test_future_slices_have_ordered_gates(self) -> None:
        text = _roadmap()
        slices = (
            "TRUTH-04",
            "SEC-BOUNDARY-01",
            "DEVEX-02",
            "DEVEX-01",
            "DEPS-01",
            "LOOP-02",
            "LOOP-03",
            "LOOP-04",
            "LOOP-05",
            "LOOP-06",
            "LOOP-07",
            "STATECORE-01",
            "FRONTEND-01",
        )
        for slice_id in slices:
            with self.subTest(slice_id=slice_id):
                self.assertIn(slice_id, text)
        self.assertIn("Only here may naming graduate", text)
        self.assertIn(
            "Until all entry criteria exist, the correct implementation is no implementation.", text
        )

    def test_roadmap_does_not_restore_wave_completion_claim(self) -> None:
        text = _roadmap()
        former_claim = "Wave 2.2 " + "complete"
        self.assertNotIn(former_claim, text)
        self.assertIn("not an Agent Work Loop", text)


if __name__ == "__main__":
    unittest.main()
