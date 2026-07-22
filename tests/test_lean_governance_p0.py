from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class LeanGovernanceP0Test(unittest.TestCase):
    def test_gitleaks_uses_bounded_pr_history_and_full_scheduled_history(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "security.yml").read_text(
                encoding="utf-8"
            )
        )
        scope = workflow["jobs"]["scope"]
        classify = scope["steps"][0]["run"]
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

        scheduled = next(
            step for step in steps if step.get("name") == "Scan full history on schedule"
        )
        self.assertEqual(
            scheduled["run"],
            "gitleaks git --config .gitleaks.toml --redact --verbose .",
        )


if __name__ == "__main__":
    unittest.main()
