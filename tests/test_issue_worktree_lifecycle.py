from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.manage_issue_worktree import (
    LifecycleError,
    WorktreeRecord,
    expected_names,
    finish_issue,
    parse_worktrees,
    validate_numbering,
)


class FakeRunner:
    def __init__(self, main: Path, worktree: Path, *, dirty: bool = False) -> None:
        self.main = main.resolve()
        self.worktree = worktree.resolve()
        self.dirty = dirty
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], cwd: Path) -> str:
        self.commands.append(command)
        if command[:4] == ["git", "worktree", "list", "--porcelain"]:
            return (
                f"worktree {self.main}\nHEAD mainhead\nbranch refs/heads/main\n\n"
                f"worktree {self.worktree}\nHEAD issuehead\n"
                "branch refs/heads/agent/336-worktree-lifecycle\n\n"
            )
        if command[:2] == ["git", "status"]:
            return " M file.py\n" if self.dirty else ""
        if command[:3] == ["gh", "issue", "view"]:
            return json.dumps(
                {"number": 336, "state": "CLOSED", "title": "worktree", "url": "issue"}
            )
        if command[:3] == ["gh", "pr", "list"]:
            return json.dumps(
                [{"number": 340, "state": "MERGED", "headRefOid": "issuehead", "url": "pr"}]
            )
        return ""


class IssueWorktreeLifecycleTest(unittest.TestCase):
    def test_parse_worktree_porcelain_including_prunable_record(self) -> None:
        records = parse_worktrees(
            "worktree /repo\nHEAD abc\nbranch refs/heads/main\n\n"
            "worktree /repo-1\nHEAD def\nbranch refs/heads/agent/1-test\nprunable stale\n\n"
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].branch, "main")
        self.assertTrue(records[1].prunable)

    def test_expected_names_bind_issue_branch_and_sibling_path(self) -> None:
        main = WorktreeRecord(Path("/repo/finharness"), "abc", "main")
        branch, path = expected_names(main, 336, "worktree-lifecycle")
        self.assertEqual(branch, "agent/336-worktree-lifecycle")
        self.assertEqual(path, Path("/repo/finharness-336"))

    def test_numbering_mismatch_is_reported(self) -> None:
        main = WorktreeRecord(Path("/repo/finharness"), "abc", "main")
        record = WorktreeRecord(Path("/repo/finharness-999"), "def", "agent/336-worktree")
        findings = validate_numbering(record, 336, main)
        self.assertIn("worktree path mismatch", findings[0])

    def test_finish_is_dry_run_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "finharness"
            worktree = Path(tmp) / "finharness-336"
            main.mkdir()
            worktree.mkdir()
            runner = FakeRunner(main, worktree)
            report = finish_issue(main, 336, apply=False, runner=runner)
            self.assertEqual(report["action"], "preview")
            self.assertFalse(
                any(
                    command[:3] == ["git", "worktree", "remove"]
                    for command in runner.commands
                )
            )

    def test_finish_refuses_dirty_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "finharness"
            worktree = Path(tmp) / "finharness-336"
            main.mkdir()
            worktree.mkdir()
            with self.assertRaisesRegex(LifecycleError, "worktree is dirty"):
                finish_issue(main, 336, apply=True, runner=FakeRunner(main, worktree, dirty=True))

    def test_finish_refuses_head_not_merged_by_pr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "finharness"
            worktree = Path(tmp) / "finharness-336"
            main.mkdir()
            worktree.mkdir()
            runner = FakeRunner(main, worktree)

            def mismatched(command: list[str], cwd: Path) -> str:
                if command[:3] == ["gh", "pr", "list"]:
                    return json.dumps(
                        [{"number": 340, "state": "MERGED", "headRefOid": "other", "url": "pr"}]
                    )
                return runner(command, cwd)

            with self.assertRaisesRegex(LifecycleError, "differs from merged PR head"):
                finish_issue(main, 336, apply=True, runner=mismatched)

    def test_finish_refuses_unmerged_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "finharness"
            worktree = Path(tmp) / "finharness-336"
            main.mkdir()
            worktree.mkdir()
            runner = FakeRunner(main, worktree)

            def unmerged(command: list[str], cwd: Path) -> str:
                if command[:3] == ["gh", "pr", "list"]:
                    return "[]"
                return runner(command, cwd)

            with self.assertRaisesRegex(LifecycleError, "found 0"):
                finish_issue(main, 336, apply=True, runner=unmerged)

    def test_successful_finish_applies_only_the_reviewed_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "finharness"
            worktree = Path(tmp) / "finharness-336"
            main.mkdir()
            worktree.mkdir()
            runner = FakeRunner(main, worktree)
            report = finish_issue(main, 336, apply=True, runner=runner)
            self.assertEqual(report["action"], "cleaned")
            self.assertIn(["git", "worktree", "remove", str(worktree.resolve())], runner.commands)
            self.assertIn(["git", "branch", "-D", "agent/336-worktree-lifecycle"], runner.commands)


if __name__ == "__main__":
    unittest.main()
