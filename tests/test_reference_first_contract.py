"""Structural contract for reference-first mechanism selection."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"


class ReferenceFirstContractTest(unittest.TestCase):
    def test_agent_and_contributor_entry_points_preserve_the_selection_order(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

        for anchor in (
            "delete or retire a duplicate mechanism",
            "use the existing canonical repository boundary",
            "standard-library, platform, official, or mature-project capability",
            "add a new abstraction only after",
            '"Future flexibility" is not evidence',
            "observed gap",
            "named replacement/deletion target",
        ):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, agents)
        self.assertIn("Reference-First Design Gate", contributing)
        self.assertIn("bounded bug fix", contributing)

    def test_mechanism_issue_forms_require_reference_first_fields(self) -> None:
        options_by_template: dict[str, list[str]] = {}
        for filename in ("architecture.yml", "implementation.yml"):
            with self.subTest(template=filename):
                template = yaml.safe_load((TEMPLATES / filename).read_text(encoding="utf-8"))
                fields = {item.get("id"): item for item in template["body"] if item.get("id")}

                self.assertIn("adoption_mode", fields)
                self.assertIn("adopt_adapt_own", fields)
                self.assertTrue(fields["adoption_mode"]["validations"]["required"])
                self.assertTrue(fields["adopt_adapt_own"]["validations"]["required"])

                options = fields["adoption_mode"]["attributes"]["options"]
                options_by_template[filename] = options
                for prefix in ("A —", "B —", "C —"):
                    self.assertTrue(any(option.startswith(prefix) for option in options))

                description = fields["adopt_adapt_own"]["attributes"]["description"]
                for required_term in (
                    "canonical repository owner",
                    "primary references",
                    "forbidden reinvention",
                    "rejected mature alternatives",
                ):
                    self.assertIn(required_term, description)

        architecture_options = options_by_template["architecture.yml"]
        implementation_options = options_by_template["implementation.yml"]
        self.assertFalse(any(option.startswith("N/A —") for option in architecture_options))
        self.assertTrue(any(option.startswith("N/A —") for option in implementation_options))


if __name__ == "__main__":
    unittest.main()
