from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def load_workflow(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


class LeanGovernanceP0Test(unittest.TestCase):
    def test_scope_classifiers_fail_closed_on_file_listing_errors(self) -> None:
        for name in (
            "browser.yml",
            "dependency-profiles.yml",
            "fuzz.yml",
            "security.yml",
        ):
            with self.subTest(workflow=name):
                classify = load_workflow(name)["jobs"]["scope"]["steps"][0]["run"]
                self.assertIn('changed_files="$(', classify)
                self.assertIn("gh api --paginate", classify)
                self.assertNotIn("done < <(", classify)
                self.assertNotIn("mapfile -t files < <(", classify)

    def test_browser_scope_includes_smoke_server_dependencies(self) -> None:
        classify = load_workflow("browser.yml")["jobs"]["scope"]["steps"][0]["run"]
        self.assertIn("scripts/run_browser_*", classify)
        self.assertIn("scripts/run_local_review_smoke_server.py", classify)

    def test_redteam_scope_includes_corpus_and_authority_boundaries(self) -> None:
        classify = load_workflow("security.yml")["jobs"]["scope"]["steps"][0]["run"]
        for path in (
            "data/redteam/*",
            "src/finharness/authorization.py",
            "src/finharness/restricted_symbols.py",
            "data/security/restricted-symbols.json",
        ):
            with self.subTest(path=path):
                self.assertIn(path, classify)

    def test_gitleaks_uses_bounded_pr_history_and_full_scheduled_history(self) -> None:
        workflow = load_workflow("security.yml")
        classify = workflow["jobs"]["scope"]["steps"][0]["run"]
        self.assertIn("gitleaks_depth=$((pr_commits + 1))", classify)

        steps = workflow["jobs"]["gitleaks"]["steps"]
        checkout = steps[0]
        self.assertEqual(
            checkout["with"]["fetch-depth"],
            "${{ github.event_name == 'schedule' && '0' || "
            "needs.scope.outputs.gitleaks_depth }}",
        )

        pr_scan = next(
            step
            for step in steps
            if step.get("name") == "Scan pull request commit range"
        )
        self.assertIn('git fetch --no-tags --depth=1 origin "$BASE_SHA"', pr_scan["run"])
        self.assertIn("gitleaks git", pr_scan["run"])
        self.assertIn('--log-opts="${BASE_SHA}..${HEAD_SHA}"', pr_scan["run"])

        main_scan = next(
            step for step in steps if step.get("name") == "Scan current main tree"
        )
        self.assertEqual(
            main_scan["run"],
            "gitleaks dir --config .gitleaks.toml --redact --verbose .",
        )

        scheduled = next(
            step for step in steps if step.get("name") == "Scan full history on schedule"
        )
        self.assertEqual(
            scheduled["run"],
            "gitleaks git --config .gitleaks.toml --redact --verbose .",
        )


if __name__ == "__main__":
    unittest.main()
