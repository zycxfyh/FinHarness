from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = REPO_ROOT / ".github" / "workflows"
PR_CONCURRENCY_GROUP = (
    "${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}"
)
PR_CANCEL_POLICY = "${{ github.event_name == 'pull_request' }}"
PR_HEAD_REF = "${{ github.event.pull_request.head.sha }}"
EVENT_SHA = "${{ github.sha }}"
IDENTITY_ACTION = "./.github/actions/verify-commit-identity"
IDENTITY_MANIFEST = ".artifacts/commit-identity-manifest.json"


def load_workflow(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class CIWorkflowContractTest(unittest.TestCase):
    def test_every_job_has_a_bounded_timeout(self) -> None:
        paths = sorted(WORKFLOW_ROOT.glob("*.yml"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(workflow=path.name):
                jobs = load_workflow(path)["jobs"]
                self.assertIsInstance(jobs, dict)
                for job_name, job in jobs.items():
                    with self.subTest(workflow=path.name, job=job_name):
                        timeout = job.get("timeout-minutes")
                        self.assertIsInstance(timeout, int)
                        self.assertGreater(timeout, 0)
                        self.assertLessEqual(timeout, 30)

    def test_pr_workflows_cancel_only_superseded_pr_runs(self) -> None:
        for path in sorted(WORKFLOW_ROOT.glob("*.yml")):
            raw = path.read_text(encoding="utf-8")
            if "pull_request:" not in raw:
                continue
            with self.subTest(workflow=path.name):
                concurrency = load_workflow(path)["concurrency"]
                self.assertEqual(concurrency["group"], PR_CONCURRENCY_GROUP)
                self.assertEqual(concurrency["cancel-in-progress"], PR_CANCEL_POLICY)

    def test_security_workflow_keeps_the_hard_kernel(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "security.yml")
        names = {job["name"] for job in workflow["jobs"].values()}
        self.assertTrue(
            {
                "Change scope",
                "Fast feedback",
                "Local verification",
                "Gitleaks",
            }.issubset(names)
        )
        scope = workflow["jobs"]["scope"]
        self.assertEqual(
            set(scope["outputs"]),
            {
                "ready",
                "docs_only",
                "python",
                "dependencies",
                "security_surface",
                "agent",
            },
        )

    def test_draft_contract_is_advisory_and_ready_contract_is_required(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "security.yml")
        fast = workflow["jobs"]["fast-feedback"]
        step = next(
            item
            for item in fast["steps"]
            if item.get("name") == "Validate pull request contract"
        )
        command = step["run"]
        self.assertIn("manage_pr_contract.py check", command)
        self.assertIn("Draft PR contract is incomplete", command)
        self.assertIn('if [[ "$IS_READY" != "true" ]]', command)
        self.assertIn('exit "$status"', command)

    def test_docs_only_and_draft_changes_skip_the_full_matrix(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "security.yml")
        local = workflow["jobs"]["local-checks"]
        local_condition = str(local["if"])
        self.assertIn("ready == 'true'", local_condition)
        self.assertIn("docs_only != 'true'", local_condition)

        fast_steps = workflow["jobs"]["fast-feedback"]["steps"]
        docs = next(
            item for item in fast_steps if item.get("name") == "Check maintained documentation"
        )
        self.assertEqual(docs["run"], "task docs:current-check")
        self.assertIn("docs_only == 'true'", docs["if"])
        self.assertIn("python == 'true'", str(workflow["jobs"]["codeql"]["if"]))
        self.assertIn(
            "security_surface == 'true'",
            str(workflow["jobs"]["trivy"]["if"]),
        )
        redteam = next(
            item
            for item in local["steps"]
            if item.get("name") == "Run promptfoo red-team boundary corpus smoke eval"
        )
        self.assertEqual(redteam["if"], "needs.scope.outputs.agent == 'true'")

    def test_local_verification_uploads_timing_and_full_stage_logs(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "security.yml")
        steps = workflow["jobs"]["local-checks"]["steps"]
        timed = next(
            step for step in steps if step.get("name") == "Run standard project checks"
        )
        upload = next(
            step for step in steps if step.get("name") == "Upload check evidence"
        )
        self.assertEqual(timed["run"], "task check:timed")
        self.assertEqual(upload["if"], "always()")
        paths = upload["with"]["path"]
        self.assertIn(".artifacts/check-timing.json", paths)
        self.assertIn(".artifacts/check-logs/", paths)
        self.assertEqual(upload["with"]["if-no-files-found"], "error")

    def test_pr_gitleaks_scans_changed_content_not_full_history(self) -> None:
        raw = (WORKFLOW_ROOT / "security.yml").read_text(encoding="utf-8")
        workflow = load_workflow(WORKFLOW_ROOT / "security.yml")
        steps = workflow["jobs"]["gitleaks"]["steps"]
        changed = next(
            step
            for step in steps
            if step.get("name") == "Scan pull request changed content"
        )
        self.assertIn("pulls/$PR_NUMBER/files", changed["run"])
        self.assertIn("--no-git", changed["run"])
        self.assertIn("Scan full history on schedule", raw)
        self.assertNotIn("fetch-depth: 0\n", raw)

    def test_required_local_verification_checks_pr_head_and_final_main(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "security.yml")
        steps = workflow["jobs"]["local-checks"]["steps"]
        checkout = steps[0]
        identity = next(
            step
            for step in steps
            if step.get("name") == "Verify Local verification checkout identity"
        )
        self.assertEqual(
            checkout["with"]["ref"],
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}",
        )
        self.assertEqual(identity["uses"], IDENTITY_ACTION)
        self.assertEqual(
            identity["with"]["claim"],
            "${{ github.event_name == 'pull_request' && 'pr_head' || 'main_commit' }}",
        )

    def test_expensive_pr_workflows_are_ready_and_scope_routed(self) -> None:
        pairs = (
            ("browser.yml", "browser-smoke"),
            ("fuzz.yml", "deterministic-fuzz-baseline"),
            ("dependency-profiles.yml", "isolated-profile"),
        )
        for workflow_name, job_name in pairs:
            with self.subTest(workflow=workflow_name):
                workflow = load_workflow(WORKFLOW_ROOT / workflow_name)
                job = workflow["jobs"][job_name]
                self.assertEqual(job["needs"], "scope")
                condition = str(job["if"])
                self.assertIn("ready == 'true'", condition)
                self.assertIn("relevant == 'true'", condition)

    def test_merge_ref_jobs_keep_exact_identity(self) -> None:
        pairs = (
            ("security.yml", "dependency-review"),
            ("security.yml", "codeql"),
            ("security.yml", "trivy"),
            ("fuzz.yml", "deterministic-fuzz-baseline"),
            ("dependency-profiles.yml", "isolated-profile"),
            ("browser.yml", "browser-smoke"),
        )
        for workflow_name, job_name in pairs:
            with self.subTest(workflow=workflow_name, job=job_name):
                steps = load_workflow(WORKFLOW_ROOT / workflow_name)["jobs"][job_name][
                    "steps"
                ]
                checkout, identity = steps[:2]
                self.assertEqual(checkout["with"]["ref"], EVENT_SHA)
                self.assertEqual(identity["uses"], IDENTITY_ACTION)
                self.assertEqual(identity["with"]["claim"], "merge_ref")
                self.assertEqual(identity["with"]["expected_sha"], EVENT_SHA)
                self.assertTrue(identity["with"]["command"])

    def test_commit_identity_workflow_proves_three_distinct_identities(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "commit-identity.yml")
        jobs = workflow["jobs"]
        pull_request_steps = jobs["pull-request-identities"]["steps"]
        main_steps = jobs["final-main-identity"]["steps"]
        identities = (
            (pull_request_steps[0], pull_request_steps[1], "pr_head", PR_HEAD_REF),
            (pull_request_steps[2], pull_request_steps[3], "merge_ref", EVENT_SHA),
            (main_steps[0], main_steps[1], "main_commit", EVENT_SHA),
        )
        for checkout, identity, claim, expected in identities:
            self.assertEqual(checkout["with"]["ref"], expected)
            self.assertEqual(identity["uses"], IDENTITY_ACTION)
            self.assertEqual(identity["with"]["claim"], claim)
            self.assertEqual(identity["with"]["expected_sha"], expected)

    def test_identity_workflow_uploads_one_manifest_per_event(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "commit-identity.yml")
        pr_job = workflow["jobs"]["pull-request-identities"]
        main_job = workflow["jobs"]["final-main-identity"]
        for job in (pr_job, main_job):
            uploads = [
                step
                for step in job["steps"]
                if "upload-artifact" in step.get("uses", "")
            ]
            self.assertEqual(len(uploads), 1)
            self.assertEqual(uploads[0]["with"]["name"], "commit-identity-manifest")
            self.assertEqual(uploads[0]["with"]["path"], IDENTITY_MANIFEST)

    def test_identity_action_owns_sha_check_outputs_and_job_summary(self) -> None:
        action = (
            REPO_ROOT / ".github" / "actions" / "verify-commit-identity" / "action.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('actual_sha="$(git rev-parse HEAD)"', action)
        self.assertIn('test "$actual_sha" = "$EXPECTED_SHA"', action)
        self.assertIn('>> "$GITHUB_OUTPUT"', action)
        self.assertIn('>> "$GITHUB_STEP_SUMMARY"', action)

    def test_base_profile_has_one_pr_owner(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "dependency-profiles.yml")
        profiles = workflow["jobs"]["isolated-profile"]["strategy"]["matrix"]["profile"]
        self.assertEqual(profiles, ["data", "research", "agent", "eval"])
        self.assertNotIn("base", profiles)

    def test_governance_stage_does_not_repeat_canonical_test_gates(self) -> None:
        taskfile = (REPO_ROOT / "Taskfile.yml").read_text(encoding="utf-8")
        body = taskfile.split("  governance:check:\n", maxsplit=1)[1].split(
            "\n  architecture:check:", maxsplit=1
        )[0]
        self.assertIn("task: governance:inventory", body)
        self.assertNotIn("unittest", body)
        self.assertNotIn("frontend/tests/", body)

    def test_optional_workflows_install_only_their_runtime_profiles(self) -> None:
        browser = (WORKFLOW_ROOT / "browser.yml").read_text(encoding="utf-8")
        fuzz = (WORKFLOW_ROOT / "fuzz.yml").read_text(encoding="utf-8")
        self.assertIn("uv sync --locked --no-default-groups", browser)
        self.assertIn("FINHARNESS_PYTHON: .venv/bin/python", browser)
        self.assertNotIn("--all-groups", browser)
        self.assertNotIn("--all-groups", fuzz)

    def test_runbook_uses_ruleset_guarded_squash_auto_merge(self) -> None:
        runbook = (
            REPO_ROOT / "docs" / "how-to" / "manage-issue-worktrees.md"
        ).read_text(encoding="utf-8")
        self.assertIn("--auto --squash --delete-branch=false", runbook)
        self.assertIn("passed `task check:ci`", runbook)
        self.assertIn("Do not use `--admin`", runbook)
        self.assertIn("link the PR with `Refs #N`, not `Closes #N`", runbook)
        self.assertIn("close the issue manually", runbook)


if __name__ == "__main__":
    unittest.main()
