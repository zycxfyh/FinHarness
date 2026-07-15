from __future__ import annotations

import unittest
from pathlib import Path

from scripts.manage_pr_contract import render_contract, validate_body

REPO_ROOT = Path(__file__).resolve().parents[1]


def _valid_body() -> str:
    return render_contract(
        issue=338,
        scope="Generate derived inventory fields and enforce concise PR metadata.",
        risk="low",
        classification="C1",
        validation=["task check:ci — passed"],
        negative_evidence="A drift fixture fails in check-only mode.",
        persistence="N/A — repository configuration only.",
        rollback="Revert the PR and restore the prior template.",
        changed_files=["scripts/manage_pr_contract.py"],
    )


class PullRequestContractTest(unittest.TestCase):
    def test_renderer_produces_a_complete_contract(self) -> None:
        body = _valid_body()
        self.assertEqual(validate_body(body), [])
        self.assertIn("Closes #338", body)
        self.assertIn("Changed files: scripts/manage_pr_contract.py", body)

    def test_missing_issue_and_manual_judgment_fail(self) -> None:
        body = (
            _valid_body()
            .replace("Closes #338", "Closes #")
            .replace(
                "- Rollback: Revert the PR and restore the prior template.",
                "- Rollback: TODO",
            )
        )
        findings = validate_body(body)
        self.assertTrue(any("Issue linkage" in finding for finding in findings))
        self.assertTrue(any("Rollback" in finding for finding in findings))

    def test_template_comments_do_not_count_as_scope_or_validation(self) -> None:
        template = (REPO_ROOT / ".github" / "pull_request_template.md").read_text(encoding="utf-8")
        findings = validate_body(template)
        self.assertTrue(any("Scope" in finding for finding in findings))
        self.assertTrue(any("Validation evidence" in finding for finding in findings))

    def test_required_dependency_review_executes_contract_check(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "security.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("name: Dependency review", workflow)
        self.assertIn("manage_pr_contract.py check --event", workflow)

    def test_ambiguous_exact_head_claim_is_rejected(self) -> None:
        body = _valid_body().replace(
            "task check:ci — passed",
            "exact-head CI — passed",
        )

        findings = validate_body(body)

        self.assertTrue(any("PR head, merge ref" in finding for finding in findings))

    def test_refs_issue_linkage_is_valid_for_post_merge_acceptance(self) -> None:
        body = _valid_body().replace("Closes #338", "Refs #338")

        self.assertEqual(validate_body(body), [])


if __name__ == "__main__":
    unittest.main()
