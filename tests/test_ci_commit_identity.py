from __future__ import annotations

import unittest

from scripts.verify_ci_commit_identity import CIContext, IdentityError, verify_identity

HEAD_SHA = "1" * 40
MERGE_SHA = "2" * 40
MAIN_SHA = "3" * 40


def _pr_context() -> CIContext:
    return CIContext(
        repository="zycxfyh/FinHarness",
        event_name="pull_request",
        github_ref="refs/pull/386/merge",
        github_sha=MERGE_SHA,
        event={
            "pull_request": {
                "number": 386,
                "head": {"sha": HEAD_SHA},
                "merge_commit_sha": MERGE_SHA,
            }
        },
    )


class CICommitIdentityTest(unittest.TestCase):
    def test_pr_head_and_merge_ref_are_distinct_valid_claims(self) -> None:
        head = verify_identity(
            claim="pr_head",
            checked_out_sha=HEAD_SHA,
            expected_sha=HEAD_SHA,
            context=_pr_context(),
            command="identity verification",
        )
        merge = verify_identity(
            claim="merge_ref",
            checked_out_sha=MERGE_SHA,
            expected_sha=MERGE_SHA,
            context=_pr_context(),
            command="identity verification",
        )

        self.assertEqual(head["result"], "passed")
        self.assertEqual(head["ref_type"], "pr_head")
        self.assertEqual(head["commit_sha"], HEAD_SHA)
        self.assertEqual(merge["result"], "passed")
        self.assertEqual(merge["ref_type"], "merge_ref")
        self.assertEqual(merge["commit_sha"], MERGE_SHA)

    def test_pr_head_proof_rejects_a_merge_ref_checkout(self) -> None:
        payload = verify_identity(
            claim="pr_head",
            checked_out_sha=MERGE_SHA,
            expected_sha=HEAD_SHA,
            context=_pr_context(),
            command="identity verification",
        )

        self.assertEqual(payload["result"], "failed")
        self.assertTrue(any("synthetic merge-ref" in item for item in payload["errors"]))

    def test_merge_ref_proof_rejects_a_pr_head_checkout(self) -> None:
        payload = verify_identity(
            claim="merge_ref",
            checked_out_sha=HEAD_SHA,
            expected_sha=MERGE_SHA,
            context=_pr_context(),
            command="identity verification",
        )

        self.assertEqual(payload["result"], "failed")
        self.assertTrue(any("PR-head SHA" in item for item in payload["errors"]))

    def test_merge_ref_proof_rejects_event_merge_sha_drift(self) -> None:
        context = _pr_context()
        context = CIContext(
            repository=context.repository,
            event_name=context.event_name,
            github_ref=context.github_ref,
            github_sha=context.github_sha,
            event={
                "pull_request": {
                    "head": {"sha": HEAD_SHA},
                    "merge_commit_sha": "4" * 40,
                }
            },
        )
        payload = verify_identity(
            claim="merge_ref",
            checked_out_sha=MERGE_SHA,
            expected_sha=MERGE_SHA,
            context=context,
            command="identity verification",
        )

        self.assertEqual(payload["result"], "failed")
        self.assertTrue(any("merge_commit_sha" in item for item in payload["errors"]))

    def test_final_main_commit_binds_push_after_sha(self) -> None:
        context = CIContext(
            repository="zycxfyh/FinHarness",
            event_name="push",
            github_ref="refs/heads/main",
            github_sha=MAIN_SHA,
            event={"after": MAIN_SHA},
        )
        payload = verify_identity(
            claim="main_commit",
            checked_out_sha=MAIN_SHA,
            expected_sha=MAIN_SHA,
            context=context,
            command="task check:timed",
        )

        self.assertEqual(payload["result"], "passed")
        self.assertEqual(payload["repository"], "zycxfyh/FinHarness")
        self.assertEqual(payload["command"], "task check:timed")

    def test_short_or_uppercase_sha_is_not_accepted_as_exact_identity(self) -> None:
        for invalid_sha in ("abc123", "A" * 40):
            with self.subTest(invalid_sha=invalid_sha), self.assertRaises(IdentityError):
                verify_identity(
                    claim="pr_head",
                    checked_out_sha=invalid_sha,
                    expected_sha=HEAD_SHA,
                    context=_pr_context(),
                    command="identity verification",
                )


if __name__ == "__main__":
    unittest.main()
