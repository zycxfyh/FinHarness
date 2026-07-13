# Manage Issue Worktrees

FinHarness keeps the main delivery rule deliberately small: one leaf issue,
one numbered branch/worktree, one PR, and no next implementation until the
current PR passes CI and merges.

## Start

Run this from any active FinHarness worktree:

```bash
task issue:start -- 336 --slug worktree-lifecycle
```

The command verifies that the issue is open, fetches current `origin/main`, and
creates the deterministic pair:

```text
branch:   agent/336-worktree-lifecycle
worktree: <main-worktree-parent>/finharness-336
```

It refuses existing paths, existing checked-out branches, malformed slugs, and
closed issues.

## Inspect

```bash
task issue:status -- 336
task issue:status
```

Status is read-only. It reports branch/path/issue-number mismatches, prunable
metadata, and dirty worktrees.

## Hand Off A Validated PR To CI

Keep the PR in draft while implementation is incomplete. After the branch has
passed `task check:ci`, push the exact validated head, mark the PR ready, and
arm squash auto-merge:

```bash
gh pr ready <pr-number>
gh pr merge <pr-number> --auto --squash --delete-branch=false
```

Do not use `--admin` to bypass the ruleset. Auto-merge waits for the active
required checks and branch rules; a failed required check blocks the merge.
The browser golden-path job remains an explicitly optional signal, so review
its result separately when the change touches the cockpit.

PR workflow runs share a per-PR concurrency group. Pushing a newer commit
cancels the superseded run for that workflow. Pushes to `main`, schedules, and
manual dispatches use unique groups instead: post-merge `main` runs remain
intentional evidence for the canonical branch and are not cancelled as stale PR
work.

## Finish After Merge

First preview the exact cleanup plan:

```bash
task issue:finish -- 336
```

Then apply it from the main worktree:

```bash
task issue:finish -- 336 --apply
```

Cleanup is allowed only when the issue is closed, exactly one merged PR exists
for the branch, the local head is the exact PR head, naming is consistent, and
the worktree is clean. The exact-head check is required because squash merges
do not make the topic commit an ancestor of `main`; ordinary `git branch -d`
cannot prove that cleanup is safe.

The command never deletes arbitrary branches, never discards a dirty worktree,
and does not delete a remote branch. Repository merge settings own remote branch
deletion.
