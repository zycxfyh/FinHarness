from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION_PATH = REPO_ROOT / ".github" / "actions" / "verify-commit-identity" / "action.yml"


def _run(*args: str, cwd: Path) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _action_script() -> str:
    action = yaml.safe_load(ACTION_PATH.read_text(encoding="utf-8"))
    return action["runs"]["steps"][0]["run"]


class CICommitIdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        _run("git", "init", "--quiet", cwd=self.repo)
        _run("git", "config", "user.name", "CI Identity Test", cwd=self.repo)
        _run("git", "config", "user.email", "ci-identity@example.invalid", cwd=self.repo)

        tracked = self.repo / "tracked.txt"
        tracked.write_text("head\n", encoding="utf-8")
        _run("git", "add", "tracked.txt", cwd=self.repo)
        _run("git", "commit", "--quiet", "-m", "head", cwd=self.repo)
        self.head_sha = _run("git", "rev-parse", "HEAD", cwd=self.repo)

        tracked.write_text("merge\n", encoding="utf-8")
        _run("git", "commit", "--quiet", "-am", "synthetic merge", cwd=self.repo)
        self.merge_sha = _run("git", "rev-parse", "HEAD", cwd=self.repo)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _verify(
        self,
        *,
        claim: str,
        expected_sha: str,
        github_sha: str,
        event_name: str = "pull_request",
        github_ref: str = "refs/pull/386/merge",
        repository: str = "zycxfyh/FinHarness",
        command: str = "identity fixture",
    ) -> subprocess.CompletedProcess[str]:
        output = self.repo / "github-output.txt"
        summary = self.repo / "github-summary.md"
        env = os.environ | {
            "IDENTITY_CLAIM": claim,
            "EXPECTED_SHA": expected_sha,
            "IDENTITY_COMMAND": command,
            "GITHUB_REPOSITORY": repository,
            "GITHUB_EVENT_NAME": event_name,
            "GITHUB_REF": github_ref,
            "GITHUB_SHA": github_sha,
            "GITHUB_OUTPUT": str(output),
            "GITHUB_STEP_SUMMARY": str(summary),
        }
        return subprocess.run(
            ["/bin/bash", "-c", _action_script()],
            cwd=self.repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    def test_pr_head_and_merge_ref_are_distinct_valid_claims(self) -> None:
        _run("git", "checkout", "--quiet", "--detach", self.head_sha, cwd=self.repo)
        head = self._verify(
            claim="pr_head",
            expected_sha=self.head_sha,
            github_sha=self.merge_sha,
        )
        self.assertEqual(head.returncode, 0, head.stderr)
        output = (self.repo / "github-output.txt").read_text(encoding="utf-8")
        self.assertIn("claim=pr_head", output)
        self.assertIn(f"commit_sha={self.head_sha}", output)

        _run("git", "checkout", "--quiet", "--detach", self.merge_sha, cwd=self.repo)
        merge = self._verify(
            claim="merge_ref",
            expected_sha=self.merge_sha,
            github_sha=self.merge_sha,
        )
        self.assertEqual(merge.returncode, 0, merge.stderr)
        output = (self.repo / "github-output.txt").read_text(encoding="utf-8")
        self.assertIn("claim=merge_ref", output)
        self.assertIn(f"commit_sha={self.merge_sha}", output)

    def test_pr_head_claim_rejects_merge_ref_checkout(self) -> None:
        result = self._verify(
            claim="pr_head",
            expected_sha=self.head_sha,
            github_sha=self.merge_sha,
        )

        self.assertNotEqual(result.returncode, 0)

    def test_merge_ref_claim_rejects_pr_head_checkout(self) -> None:
        _run("git", "checkout", "--quiet", "--detach", self.head_sha, cwd=self.repo)
        result = self._verify(
            claim="merge_ref",
            expected_sha=self.merge_sha,
            github_sha=self.merge_sha,
        )

        self.assertNotEqual(result.returncode, 0)

    def test_final_main_claim_binds_main_push_sha(self) -> None:
        result = self._verify(
            claim="main_commit",
            expected_sha=self.merge_sha,
            github_sha=self.merge_sha,
            event_name="push",
            github_ref="refs/heads/main",
            command="task check:timed",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        output = (self.repo / "github-output.txt").read_text(encoding="utf-8")
        self.assertIn("claim=main_commit", output)
        self.assertIn("command=task check:timed", output)

    def test_repository_and_command_fail_closed(self) -> None:
        for repository, command in (("", "identity fixture"), ("zycxfyh/FinHarness", "")):
            with self.subTest(repository=repository, command=command):
                result = self._verify(
                    claim="merge_ref",
                    expected_sha=self.merge_sha,
                    github_sha=self.merge_sha,
                    repository=repository,
                    command=command,
                )
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
