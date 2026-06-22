from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts import vocab_lint


class VocabLintTest(unittest.TestCase):
    def test_overclaim_is_reported_without_nearby_non_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "formal.md"
            path.write_text("This strategy is safe to trade.\n", encoding="utf-8")

            findings = vocab_lint.run([path])

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "safe_to_trade")

    def test_non_claim_allows_otherwise_risky_phrase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "formal.md"
            path.write_text(
                "This result is supported at rung X.\n"
                "Not claimed: edge proven or execution authorization.\n",
                encoding="utf-8",
            )

            findings = vocab_lint.run([path])

        self.assertEqual(findings, [])

    def test_project_term_without_anchor_is_warned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "formal.md"
            path.write_text("B4 lineage is required here.\n", encoding="utf-8")

            findings = vocab_lint.run([path])

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].rule, "project_term_anchor")
        self.assertEqual(findings[0].severity, "warn")

    def test_glossary_anchor_suppresses_project_term_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "formal.md"
            path.write_text(
                "See docs/reference/glossary.md.\n"
                "B4 lineage is required here.\n",
                encoding="utf-8",
            )

            findings = vocab_lint.run([path])

        self.assertEqual(findings, [])

    def test_blocked_language_constant_context_is_exempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "formal.py"
            path.write_text(
                "BLOCKED_LANGUAGE = [\n"
                '    "ready to trade",\n'
                '    "trade recommendation",\n'
                "]\n",
                encoding="utf-8",
            )

            findings = vocab_lint.run([path])

        self.assertEqual(findings, [])

    def test_thought_layer_paths_are_exempt(self) -> None:
        path = vocab_lint.ROOT / "docs" / "think" / "note.md"

        self.assertTrue(vocab_lint.is_exempt(path))


if __name__ == "__main__":
    unittest.main()
