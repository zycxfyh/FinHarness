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
