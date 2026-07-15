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
REQUIRED_SECURITY_CHECKS = {
    "Local verification",
    "Dependency review",
    "Gitleaks",
    "Trivy filesystem scan",
    "CodeQL",
}
PR_HEAD_REF = "${{ github.event.pull_request.head.sha }}"
EVENT_SHA = "${{ github.sha }}"


def load_workflow(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class CIWorkflowContractTest(unittest.TestCase):
    def test_every_job_has_a_bounded_timeout(self) -> None:
        paths = sorted(WORKFLOW_ROOT.glob("*.yml"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(workflow=path.name):
                workflow = load_workflow(path)
                jobs = workflow["jobs"]
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

    def test_active_required_security_check_names_are_preserved(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "security.yml")
        actual = {job["name"] for job in workflow["jobs"].values()}
        self.assertEqual(actual, REQUIRED_SECURITY_CHECKS)

    def test_local_verification_records_timing_even_when_checks_fail(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "security.yml")
        steps = workflow["jobs"]["local-checks"]["steps"]
        timed = next(step for step in steps if step.get("name") == "Run standard project checks")
        upload = next(step for step in steps if step.get("name") == "Upload check timing evidence")

        self.assertEqual(timed["run"], "task check:timed")
        self.assertEqual(upload["if"], "always()")
        self.assertEqual(upload["with"]["path"], ".artifacts/check-timing.json")
        self.assertEqual(upload["with"]["if-no-files-found"], "error")

    def test_local_verification_has_one_dependency_setup_owner(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "security.yml")
        steps = workflow["jobs"]["local-checks"]["steps"]
        commands = "\n".join(str(step.get("run", "")) for step in steps)

        self.assertNotIn("uv sync", commands)
        self.assertNotIn("pnpm install", commands)
        self.assertIn("task check:timed", commands)

    def test_commit_identity_workflow_proves_three_distinct_identities(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "commit-identity.yml")
        jobs = workflow["jobs"]

        head = jobs["pr-head-identity"]
        merge = jobs["merge-ref-identity"]
        main = jobs["main-commit-identity"]
        self.assertEqual(head["steps"][0]["with"]["ref"], PR_HEAD_REF)
        self.assertEqual(merge["steps"][0]["with"]["ref"], EVENT_SHA)
        self.assertEqual(main["steps"][0]["with"]["ref"], EVENT_SHA)
        self.assertIn("--claim pr_head", head["steps"][1]["run"])
        self.assertIn("--claim merge_ref", merge["steps"][1]["run"])
        self.assertIn("--claim main_commit", main["steps"][1]["run"])
        for job in (head, merge, main):
            upload = job["steps"][2]
            self.assertEqual(upload["if"], "always()")
            self.assertEqual(
                upload["with"]["path"],
                ".artifacts/ci-commit-identity.json",
            )

    def test_required_local_verification_checks_pr_head_and_final_main(self) -> None:
        workflow = load_workflow(WORKFLOW_ROOT / "security.yml")
        steps = workflow["jobs"]["local-checks"]["steps"]
        checkout = steps[0]
        identity = next(
            step for step in steps if step.get("name") == "Verify local-check commit identity"
        )

        self.assertEqual(
            checkout["with"]["ref"],
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}",
        )
        self.assertIn('--claim "$IDENTITY_CLAIM"', identity["run"])
        self.assertEqual(
            identity["env"]["EXPECTED_SHA"],
            "${{ github.event_name == 'pull_request' && "
            "github.event.pull_request.head.sha || github.sha }}",
        )

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
        taskfile = (REPO_ROOT / "Taskfile.yml").read_text(encoding="utf-8")
        self.assertIn("UV_PROJECT_ENVIRONMENT=.venv-probes/fuzz", taskfile)

    def test_runbook_uses_ruleset_guarded_squash_auto_merge(self) -> None:
        runbook = (REPO_ROOT / "docs" / "how-to" / "manage-issue-worktrees.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("--auto --squash --delete-branch=false", runbook)
        self.assertIn("passed `task check:ci`", runbook)
        self.assertIn("Do not use `--admin`", runbook)


if __name__ == "__main__":
    unittest.main()
