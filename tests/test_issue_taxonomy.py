"""Contracts for GitHub-native plane, kind, and lifecycle taxonomy."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml
from scripts.audit_issue_taxonomy import TAXONOMY, validate_issues

ROOT = Path(__file__).resolve().parents[1]
FORMS = ROOT / ".github" / "ISSUE_TEMPLATE"
EXPECTED_FORM_KINDS = {
    "architecture.yml": "type:adr",
    "bug.yml": "type:feature",
    "deferred.yml": "type:deferred-gate",
    "experiment.yml": "type:experiment",
    "implementation.yml": "type:feature",
}


def _issue(number: int, *labels: str) -> dict[str, object]:
    return {"number": number, "title": f"Issue {number}", "labels": list(labels)}


class IssueTaxonomyAuditTest(unittest.TestCase):
    def test_repository_exposes_one_live_read_only_issue_audit(self) -> None:
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        taskfile = (ROOT / "Taskfile.yml").read_text(encoding="utf-8")
        command_reference = (ROOT / "docs" / "reference" / "commands.md").read_text(
            encoding="utf-8"
        )
        how_to = (ROOT / "docs" / "how-to" / "audit-issue-backlog.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("GitHub is the mutable work-state system", agents)
        for lifecycle in ("status:active", "status:dormant", "status:deferred"):
            with self.subTest(lifecycle=lifecycle):
                self.assertIn(lifecycle, agents)
        self.assertIn("issues:audit:", taskfile)
        self.assertIn("scripts/audit_issue_taxonomy.py", taskfile)
        self.assertIn("task issues:audit", command_reference)
        self.assertIn("does not mirror live", how_to)
        self.assertIn("status:dormant", how_to)
        self.assertIn("status:deferred", how_to)

    def test_complete_single_cardinality_issue_passes(self) -> None:
        findings = validate_issues(
            [_issue(1, "plane:truth", "type:feature", "status:active", "priority:P0")]
        )
        self.assertEqual(findings, [])

    def test_missing_multiple_and_unknown_dimensions_fail(self) -> None:
        findings = validate_issues(
            [
                _issue(1, "type:feature", "status:active"),
                _issue(2, "plane:truth", "plane:knowledge", "type:feature", "status:dormant"),
                _issue(3, "plane:other", "type:feature", "status:active"),
                _issue(4, "plane:agent", "type:feature", "status:active", "status:deferred"),
            ]
        )
        self.assertIn("#1 plane: expected exactly one label, found 0 (none)", findings)
        self.assertIn(
            "#2 plane: expected exactly one label, found 2 (plane:knowledge, plane:truth)",
            findings,
        )
        self.assertIn("#3 plane: unknown label plane:other", findings)
        self.assertIn(
            "#4 lifecycle: expected exactly one label, found 2 (status:active, status:deferred)",
            findings,
        )

    def test_issue_forms_declare_plane_and_lifecycle_for_review(self) -> None:
        form_paths = sorted(path for path in FORMS.glob("*.yml") if path.name != "config.yml")
        self.assertEqual({path.name for path in form_paths}, set(EXPECTED_FORM_KINDS))
        for path in form_paths:
            with self.subTest(form=path.name):
                form = yaml.safe_load(path.read_text(encoding="utf-8"))
                labels = set(form.get("labels", []))
                kind_labels = {label for label in labels if label.startswith("type:")}
                plane_labels = {label for label in labels if label.startswith("plane:")}
                lifecycle_labels = {
                    label for label in labels if label.startswith("status:")
                }

                self.assertEqual(kind_labels, {EXPECTED_FORM_KINDS[path.name]})
                self.assertEqual(plane_labels, set())

                fields = {item.get("id"): item for item in form["body"] if item.get("id")}
                self.assertTrue(fields["primary_plane"]["validations"]["required"])
                self.assertTrue(fields["lifecycle"]["validations"]["required"])

                plane_options = fields["primary_plane"]["attributes"]["options"]
                self.assertEqual(
                    {option.split(" —", maxsplit=1)[0] for option in plane_options},
                    TAXONOMY["plane"],
                )
                lifecycle_options = fields["lifecycle"]["attributes"]["options"]
                declared = {option.split(" —", maxsplit=1)[0] for option in lifecycle_options}
                if path.name == "deferred.yml":
                    self.assertEqual(lifecycle_labels, {"status:deferred"})
                    self.assertEqual(declared, {"status:deferred"})
                else:
                    self.assertEqual(lifecycle_labels, set())
                    self.assertEqual(declared, TAXONOMY["lifecycle"])


if __name__ == "__main__":
    unittest.main()
